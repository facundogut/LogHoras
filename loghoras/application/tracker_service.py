from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from loghoras.domain.time_tracking import (
    calculate_working_hours,
    first_business_moment_of_year_month,
    month_filename,
    month_key,
    parse_jira_datetime,
    last_business_moment_of_year_month,
)
from loghoras.infrastructure.jira_client import JiraClient
from loghoras.infrastructure.log_repository import MonthlyLogRepository
from loghoras.shared.config import TrackerConfig


class JiraTrackerService:
    def __init__(self, config: TrackerConfig, jira_client: JiraClient, repository: MonthlyLogRepository):
        self.config = config
        self.jira_client = jira_client
        self.repository = repository

    def update_log_entries(self, now: datetime) -> list[dict[str, Any]]:
        logs_cache: dict[str, dict[str, Any]] = {}
        novedades_set: set[tuple[str, str, str]] = set()
        novedades: list[dict[str, Any]] = []
        month_start_now = first_business_moment_of_year_month(now.year, now.month, now.tzinfo, self.config)

        def get_log_for(dt: datetime) -> dict[str, Any]:
            key = month_key(dt)
            if key not in logs_cache:
                logs_cache[key] = self.repository.load_month_log(dt)
            return logs_cache[key]

        def save_all_logs() -> None:
            for key, data in logs_cache.items():
                year, month = map(int, key.split('-'))
                self.repository.save_month_log(datetime(year, month, 1, tzinfo=now.tzinfo), data)

        def find_open_entry_in_month(month_dt: datetime, issue_id: str):
            key = month_key(month_dt)
            if key not in logs_cache:
                path = month_filename(month_dt, self.config)
                if not os.path.exists(path):
                    return None, None, None
                logs_cache[key] = self.repository.load_month_log(month_dt)
            log = get_log_for(month_dt)
            for log_key, item in log.items():
                if item.get('issue_id') != issue_id:
                    continue
                for entry in item.get('entries', []):
                    if entry.get('exited_at') is None:
                        return log_key, item, entry
            return None, None, None

        def find_open_entry_anywhere(issue_id: str, months_back: int = 24):
            year, month = now.year, now.month
            for _ in range(months_back):
                current_month = datetime(year, month, 1, tzinfo=now.tzinfo)
                log_key, item, entry = find_open_entry_in_month(current_month, issue_id)
                if entry:
                    return current_month, log_key, item, entry
                month -= 1
                if month == 0:
                    month = 12
                    year -= 1
            return None, None, None, None

        def exists_closed_entry(month_dt: datetime, issue_id: str, entered_iso: str, exited_iso: str) -> bool:
            key = month_key(month_dt)
            if key not in logs_cache:
                path = month_filename(month_dt, self.config)
                if not os.path.exists(path):
                    return False
                logs_cache[key] = self.repository.load_month_log(month_dt)
            for item in get_log_for(month_dt).values():
                if item.get('issue_id') != issue_id:
                    continue
                for entry in item.get('entries', []):
                    if entry.get('entered_at') == entered_iso and entry.get('exited_at') == exited_iso:
                        return True
            return False

        def add_novedad(issue_key: str, assignee_id: str, summary: str, link: str, issue_id: str, entered_iso: str, exited_iso: str | None):
            novel_key = (issue_id, entered_iso, exited_iso or 'OPEN')
            if novel_key in novedades_set:
                return
            novedades_set.add(novel_key)
            novedades.append({'issue_key': issue_key, 'assignee_id': assignee_id, 'summary': summary, 'link': link})

        def upsert_closed_global(month_dt: datetime, issue_id: str, entered_iso: str, exited_iso: str) -> str:
            start_dt = parse_jira_datetime(entered_iso)
            end_dt = parse_jira_datetime(exited_iso)
            if not start_dt or not end_dt or end_dt <= start_dt:
                return 'noop'
            _, _, open_item, open_entry = find_open_entry_anywhere(issue_id)
            if open_entry is not None:
                open_entry['exited_at'] = exited_iso
                open_entry['worked_hours'] = calculate_working_hours(parse_jira_datetime(open_entry['entered_at']), end_dt, self.config)
                open_item['entries'].sort(key=lambda item: (item.get('entered_at') or ''))
                return 'updated'
            if exists_closed_entry(month_dt, issue_id, entered_iso, exited_iso):
                return 'noop'
            return 'insert'

        issues = self.jira_client.get_current_issues()
        exited = self.jira_client.get_recently_exited_issues()
        unique_issues = {issue['id']: issue for issue in issues + exited}
        issues = list(unique_issues.values())
        doing_ids = {issue['id'] for issue in self.jira_client.get_current_issues()}

        def close_stray_open_entries() -> None:
            months_to_check = [datetime(now.year, now.month, 1, tzinfo=now.tzinfo)]
            previous_year = now.year if now.month > 1 else now.year - 1
            previous_month = now.month - 1 if now.month > 1 else 12
            months_to_check.append(datetime(previous_year, previous_month, 1, tzinfo=now.tzinfo))
            for month_dt in months_to_check:
                month_cache_key = month_key(month_dt)
                if not os.path.exists(month_filename(month_dt, self.config)):
                    continue
                if month_cache_key not in logs_cache:
                    logs_cache[month_cache_key] = self.repository.load_month_log(month_dt)
                for item in list(get_log_for(month_dt).values()):
                    issue_id = item.get('issue_id')
                    if issue_id in doing_ids:
                        continue
                    for entry in item.get('entries', []):
                        if entry.get('exited_at') is not None or not entry.get('entered_at'):
                            continue
                        exited_ts_real = None
                        try:
                            issue_key = item.get('issue_key')
                            if issue_key:
                                _, exited_ts_real = self.jira_client.get_transition_times(issue_key, issue_id)
                        except Exception:
                            exited_ts_real = None
                        if not exited_ts_real:
                            exited_ts_real = now
                        start_dt = parse_jira_datetime(entry.get('entered_at'))
                        if not start_dt or exited_ts_real <= start_dt:
                            continue
                        entered_iso = entry['entered_at']
                        exited_iso = exited_ts_real.isoformat()
                        if exists_closed_entry(month_dt, issue_id, entered_iso, exited_iso):
                            continue
                        entry['exited_at'] = exited_iso
                        entry['worked_hours'] = calculate_working_hours(start_dt, exited_ts_real, self.config)
                    item['entries'].sort(key=lambda current_entry: (current_entry.get('entered_at') or ''))

        for issue in issues:
            issue_key = issue.get('key')
            fields = issue.get('fields', {})
            issue_id = issue.get('id')
            assignee = fields.get('assignee') or {}
            assignee_id = assignee.get('name') or 'Unassigned'
            assignee_name = assignee.get('displayName') or 'Unassigned'
            summary = fields.get('summary', '')
            link = self.jira_client.build_issue_link(issue_key)
            item_key = f'{issue_id}-{assignee_id}'
            entered_ts, exited_ts = self.jira_client.get_transition_times(issue_key, issue_id)

            def ensure_item(month_dt: datetime) -> dict[str, Any]:
                log = get_log_for(month_dt)
                item = log.get(item_key)
                if not item:
                    item = {
                        'issue_key': issue_key,
                        'issue_id': issue_id,
                        'assignee_id': assignee_id,
                        'assignee_name': assignee_name,
                        'summary': summary,
                        'entries': [],
                    }
                    log[item_key] = item
                else:
                    item['assignee_name'] = assignee_name
                    item['summary'] = summary
                return item

            def find_entry(entries: list[dict[str, Any]], entered_iso: str, exited_iso: str | None):
                for entry in entries:
                    if entry.get('entered_at') == entered_iso and entry.get('exited_at') == exited_iso:
                        return entry
                return None

            if entered_ts and (not exited_ts or exited_ts < entered_ts):
                current_start = max(entered_ts, month_start_now)
                if current_start > now:
                    continue
                while month_key(current_start) != month_key(now):
                    year, month = current_start.year, current_start.month
                    segment_end = last_business_moment_of_year_month(year, month, current_start.tzinfo, self.config)
                    if segment_end <= current_start:
                        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
                        current_start = first_business_moment_of_year_month(next_year, next_month, current_start.tzinfo, self.config)
                        continue
                    entered_iso = current_start.isoformat()
                    exited_iso = segment_end.isoformat()
                    if upsert_closed_global(current_start, issue_id, entered_iso, exited_iso) == 'insert':
                        item = ensure_item(current_start)
                        item['entries'].append({'entered_at': entered_iso, 'exited_at': exited_iso, 'worked_hours': calculate_working_hours(current_start, segment_end, self.config)})
                        item['entries'].sort(key=lambda entry: (entry.get('entered_at') or ''))
                        add_novedad(issue_key, assignee_id, summary, link, issue_id, entered_iso, exited_iso)
                    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
                    current_start = first_business_moment_of_year_month(next_year, next_month, current_start.tzinfo, self.config)
                entered_iso = current_start.isoformat()
                worked_hours = calculate_working_hours(current_start, now, self.config)
                _, open_item, open_entry = find_open_entry_in_month(now, issue_id)
                if open_entry:
                    if open_entry.get('worked_hours') != worked_hours:
                        open_entry['worked_hours'] = worked_hours
                    open_item['entries'].sort(key=lambda entry: (entry.get('entered_at') or ''))
                else:
                    item = ensure_item(now)
                    if not find_entry(item['entries'], entered_iso, None):
                        item['entries'].append({'entered_at': entered_iso, 'exited_at': None, 'worked_hours': worked_hours})
                        add_novedad(issue_key, assignee_id, summary, link, issue_id, entered_iso, None)
                        item['entries'].sort(key=lambda entry: (entry.get('entered_at') or ''))
            elif entered_ts and exited_ts and exited_ts >= entered_ts:
                if exited_ts <= month_start_now:
                    continue
                segment_start = max(entered_ts, month_start_now)
                if segment_start >= exited_ts:
                    continue
                while segment_start < exited_ts and month_key(segment_start) != month_key(exited_ts):
                    year, month = segment_start.year, segment_start.month
                    segment_end = last_business_moment_of_year_month(year, month, segment_start.tzinfo, self.config)
                    if segment_end <= segment_start:
                        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
                        segment_start = first_business_moment_of_year_month(next_year, next_month, segment_start.tzinfo, self.config)
                        continue
                    entered_iso = segment_start.isoformat()
                    exited_iso = segment_end.isoformat()
                    if upsert_closed_global(segment_start, issue_id, entered_iso, exited_iso) == 'insert':
                        item = ensure_item(segment_start)
                        item['entries'].append({'entered_at': entered_iso, 'exited_at': exited_iso, 'worked_hours': calculate_working_hours(segment_start, segment_end, self.config)})
                        item['entries'].sort(key=lambda entry: (entry.get('entered_at') or ''))
                        add_novedad(issue_key, assignee_id, summary, link, issue_id, entered_iso, exited_iso)
                    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
                    segment_start = first_business_moment_of_year_month(next_year, next_month, segment_start.tzinfo, self.config)
                if exited_ts > segment_start:
                    entered_iso = segment_start.isoformat()
                    exited_iso = exited_ts.isoformat()
                    if upsert_closed_global(exited_ts, issue_id, entered_iso, exited_iso) == 'insert':
                        item = ensure_item(exited_ts)
                        item['entries'].append({'entered_at': entered_iso, 'exited_at': exited_iso, 'worked_hours': calculate_working_hours(segment_start, exited_ts, self.config)})
                        item['entries'].sort(key=lambda entry: (entry.get('entered_at') or ''))
                        add_novedad(issue_key, assignee_id, summary, link, issue_id, entered_iso, exited_iso)

        close_stray_open_entries()
        save_all_logs()
        return novedades
