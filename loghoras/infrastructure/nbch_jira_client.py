from __future__ import annotations

from datetime import datetime
from typing import Any

import requests

from loghoras.domain.time_tracking import parse_jira_datetime
from loghoras.shared.config import TrackerConfig


def jql_quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def build_status_in_clause(statuses: list[str]) -> str:
    return ', '.join(jql_quote(status) for status in statuses)


class NbchJiraClient:
    def __init__(self, config: TrackerConfig):
        self.config = config
        self.scope = self._build_scope_clause()

    def _build_scope_clause(self) -> str:
        parts = ['(labels != ATDATOS OR labels IS EMPTY)']
        if self.config.project_keys:
            parts.append('project in ({})'.format(', '.join(self.config.project_keys)))
        parts.append('assignee in ({})'.format(', '.join(self.config.assignees)))
        return ' AND '.join(parts)

    def build_issue_link(self, issue_key: str) -> str:
        return f"{self.config.jira_url.rstrip('/')}/browse/{issue_key}"

    def get_current_issues(self) -> list[dict[str, Any]]:
        jql = f'{self.scope} AND status in ({build_status_in_clause(self.config.status_target)})'
        return self._search_issues(jql, 'Error JIRA search')

    def get_recently_exited_issues(self) -> list[dict[str, Any]]:
        jql = (
            f'{self.scope} AND status CHANGED FROM in '
            f'({build_status_in_clause(self.config.status_target)}) AFTER startOfMonth(-1)'
        )
        return self._search_issues(jql, 'Error JIRA search (recent exits)')

    def _search_issues(self, jql: str, error_prefix: str) -> list[dict[str, Any]]:
        base_url = self.config.jira_url.rstrip('/')
        url = f'{base_url}/rest/api/2/search'
        start_at = 0
        all_issues: list[dict[str, Any]] = []
        while True:
            params = {'jql': jql, 'fields': self.config.fields, 'startAt': start_at, 'maxResults': 100}
            response = requests.get(
                url,
                headers=self.config.headers,
                params=params,
                timeout=self.config.request_timeout,
                verify=self.config.verify_ssl,
            )
            if response.status_code != 200:
                raise RuntimeError(f'{error_prefix}: {response.status_code} - {response.text}')
            data = response.json()
            issues = data.get('issues', [])
            all_issues.extend(issues)
            total = data.get('total', len(issues))
            if start_at + len(issues) >= total:
                return all_issues
            start_at += len(issues)

    def get_all_changelog(self, issue_key: str, issue_id: str | None = None) -> list[dict[str, Any]]:
        def fetch_paged(path_base: str) -> list[dict[str, Any]] | None:
            start_at = 0
            entries: list[dict[str, Any]] = []
            while True:
                base_url = self.config.jira_url.rstrip('/')
                url = f'{base_url}/rest/api/2/issue/{path_base}/changelog'
                response = requests.get(
                    url,
                    headers=self.config.headers,
                    params={'startAt': start_at, 'maxResults': 100},
                    timeout=self.config.request_timeout,
                    verify=self.config.verify_ssl,
                )
                if response.status_code == 404:
                    return None
                response.raise_for_status()
                data = response.json()
                chunk = data.get('values')
                if chunk is None:
                    return None
                entries.extend(chunk)
                total = data.get('total', start_at + len(chunk))
                max_results = data.get('maxResults', 100)
                if start_at + len(chunk) >= total:
                    entries.sort(key=lambda history: history.get('created'))
                    return entries
                start_at += max_results

        histories = fetch_paged(issue_key)
        if histories is not None:
            return histories
        if issue_id:
            histories = fetch_paged(issue_id)
            if histories is not None:
                return histories

        path_bases = [issue_key, issue_id] if issue_id else [issue_key]
        for path_base in path_bases:
            if not path_base:
                continue
            base_url = self.config.jira_url.rstrip('/')
            url = f'{base_url}/rest/api/2/issue/{path_base}'
            response = requests.get(
                url,
                headers=self.config.headers,
                params={'expand': 'changelog'},
                timeout=self.config.request_timeout,
                verify=self.config.verify_ssl,
            )
            if response.status_code == 404:
                continue
            response.raise_for_status()
            data = response.json()
            histories = (data.get('changelog', {}) or {}).get('histories', []) or []
            histories.sort(key=lambda history: history.get('created'))
            return histories
        raise RuntimeError('No se pudo obtener el changelog: ni paginado ni via expand=changelog.')

    def get_transition_times(self, issue_key: str, issue_id: str | None = None) -> tuple[datetime | None, datetime | None]:
        histories = self.get_all_changelog(issue_key, issue_id)
        transitions: list[tuple[str | None, str | None, datetime | None]] = []
        for history in histories:
            created = parse_jira_datetime(history.get('created'))
            for item in history.get('items', []):
                if item.get('field') == 'status':
                    transitions.append((item.get('fromString'), item.get('toString'), created))

        last_entered = None
        last_exited = None
        open_since = None
        for index, (current_from, current_to, timestamp) in enumerate(transitions):
            if current_to in self.config.status_target:
                last_entered = timestamp
                has_exit = any(next_transition[0] in self.config.status_target for next_transition in transitions[index + 1:])
                if not has_exit:
                    open_since = timestamp

        for current_from, _, timestamp in transitions:
            if current_from in self.config.status_target and ((last_exited is None) or (timestamp and timestamp > last_exited)):
                last_exited = timestamp

        return (open_since or last_entered), last_exited
