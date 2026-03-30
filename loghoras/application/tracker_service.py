from __future__ import annotations

from datetime import datetime
from typing import Any

from loghoras.domain.time_tracking import calculate_working_hours
from loghoras.infrastructure.nbch_jira_client import NbchJiraClient
from loghoras.infrastructure.log_repository import MonthlyLogRepository
from loghoras.shared.config import TrackerConfig


class JiraTrackerService:
    """Servicio mínimo para registrar únicamente issues activas en estado DOING."""

    def __init__(self, config: TrackerConfig, jira_client: NbchJiraClient, repository: MonthlyLogRepository):
        self.config = config
        self.jira_client = jira_client
        self.repository = repository

    def build_active_log(self, now: datetime) -> dict[str, Any]:
        active_log: dict[str, Any] = {}
        issues = self.jira_client.get_current_issues()

        for issue in issues:
            issue_key = issue.get('key')
            issue_id = issue.get('id')
            fields = issue.get('fields', {})
            assignee = fields.get('assignee') or {}
            assignee_id = assignee.get('name') or 'Unassigned'
            assignee_name = assignee.get('displayName') or 'Unassigned'
            summary = fields.get('summary', '')

            entered_ts, _ = self.jira_client.get_transition_times(issue_key, issue_id)
            if not entered_ts:
                entered_ts = now

            active_log[f'{issue_id}-{assignee_id}'] = {
                'issue_key': issue_key,
                'issue_id': issue_id,
                'assignee_id': assignee_id,
                'assignee_name': assignee_name,
                'summary': summary,
                'link': self.jira_client.build_issue_link(issue_key),
                'entries': [
                    {
                        'entered_at': entered_ts.isoformat(),
                        'exited_at': None,
                        'worked_hours': calculate_working_hours(entered_ts, now, self.config),
                    }
                ],
            }

        return active_log

    def update_log_entries(self, now: datetime) -> str:
        active_log = self.build_active_log(now)
        self.repository.save_month_log(now, active_log)
        return str(self.repository.month_log_path(now).resolve())
