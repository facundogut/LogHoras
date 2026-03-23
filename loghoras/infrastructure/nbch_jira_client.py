from __future__ import annotations

import json
import time
from typing import Any

import requests

from loghoras.shared.nbch_config import NbchSyncConfig


class NbchJiraClient:
    def __init__(self, config: NbchSyncConfig):
        self.config = config

    def _req_with_backoff(self, method: str, url: str, **kwargs) -> requests.Response:
        response = None
        for attempt in range(4):
            response = requests.request(
                method,
                url,
                headers=self.config.headers,
                auth=self.config.auth,
                verify=not self.config.ssl_no_verify,
                timeout=self.config.request_timeout,
                **kwargs,
            )
            if response.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            return response
        return response

    def jira_get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        response = self._req_with_backoff('GET', f'{self.config.jira_url}{path}', params=params)
        if response.status_code >= 400:
            try:
                details = response.json()
            except Exception:
                details = response.text
            raise RuntimeError(f'GET {path} fallo: {response.status_code} -> {details}')
        return response.json()

    def jira_post_json(self, path: str, payload: dict[str, Any]) -> Any:
        response = self._req_with_backoff('POST', f'{self.config.jira_url}{path}', data=json.dumps(payload))
        if response.status_code >= 400:
            try:
                details = response.json()
            except Exception:
                details = response.text
            raise RuntimeError(f'POST {path} fallo: {response.status_code} -> {details}')
        return response.json()

    def build_issue_link(self, key: str) -> str:
        return f'{self.config.jira_url}/browse/{key}'

    def search_existing_by_cds(self, cds_num: str) -> dict[str, Any] | None:
        jql = (
            f'project = {self.config.jira_project} AND ('
            f'summary ~ "\\"CDS {cds_num}\\"" OR '
            f'summary ~ "\\"CDS-{cds_num}\\"" OR '
            f'summary ~ "\\"CDS -{cds_num}\\"" OR '
            f'summary ~ "\\"CDS- {cds_num}\\"")'
        )
        body = {'jql': jql, 'fields': ['key', 'summary', 'assignee'], 'maxResults': 5}
        try:
            result = self.jira_post_json('/rest/api/3/search/jql', body)
        except RuntimeError as error:
            if '410' in str(error):
                raise
            result = self.jira_get_json(
                '/rest/api/3/search/jql',
                params={'jql': jql, 'fields': 'key,summary,assignee', 'maxResults': 5},
            )
        issues = result.get('issues', [])
        return issues[0] if issues else None

    def resolve_assignee(self, assignee_id: str) -> tuple[str | None, str]:
        display_name = self.config.cds_user_to_name.get(assignee_id, assignee_id)
        if assignee_id in self.config.cds_user_to_cloud_account:
            return self.config.cds_user_to_cloud_account[assignee_id], display_name
        try:
            users = self.jira_get_json('/rest/api/3/user/search', params={'query': assignee_id})
            if users:
                return users[0].get('accountId'), users[0].get('displayName', display_name)
        except Exception:
            pass
        return None, display_name

    def make_issue_payload(self, summary: str, issue_type: str, assignee_account: str | None) -> dict[str, Any]:
        fields = {
            'project': {'key': self.config.jira_project},
            'summary': summary,
            'issuetype': {'id': issue_type},
            'reporter': {'accountId': self.config.reporter_account_id},
            'customfield_11203': {'id': self.config.project_field_id},
            'customfield_11900': {'id': self.config.account_field_id},
            'customfield_10025': {'id': self.config.module_field_id},
            'io.tempo.jira__account': self.config.tempo_account_id,
            'description': {
                'type': 'doc',
                'version': 1,
                'content': [
                    {
                        'type': 'paragraph',
                        'content': [
                            {'type': 'text', 'text': 'Asignación de tareas según disponibilidad horaria del equipo'}
                        ],
                    }
                ],
            },
        }
        if assignee_account:
            fields['assignee'] = {'accountId': assignee_account}
        return {'fields': fields}

    def create_issue(self, summary: str, issue_type: str, assignee_id: str) -> tuple[str, str]:
        account_id, _ = self.resolve_assignee(assignee_id)
        payload = self.make_issue_payload(summary, issue_type, account_id)
        result = self.jira_post_json('/rest/api/3/issue', payload)
        return result['key'], result.get('self', '')
