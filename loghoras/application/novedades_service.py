from __future__ import annotations

import sys
import time
from typing import Any

from loghoras.domain.novedades import build_summary, extract_cds_number
from loghoras.infrastructure.issue_type_client import IssueTypeClient
from loghoras.infrastructure.topaz_jira_client import TopazJiraClient
from loghoras.infrastructure.novedades_repository import NovedadesRepository


class NovedadesSyncService:
    def __init__(
        self,
        repository: NovedadesRepository,
        jira_client: TopazJiraClient,
        issue_type_client: IssueTypeClient,
        user_names: dict[str, str],
    ):
        self.repository = repository
        self.jira_client = jira_client
        self.issue_type_client = issue_type_client
        self.user_names = user_names

    def sync(self, input_path: str, output_path: str) -> list[dict[str, Any]]:
        novedades = self.repository.load_novedades(input_path)
        created_issues: list[dict[str, Any]] = []
        for item in novedades:
            issue_key = str(item['issue_key']).strip()
            assignee_id = str(item['assignee_id']).strip()
            summary_source = str(item['summary']).strip()
            source_link = str(item['link']).strip()

            cds_num = extract_cds_number(issue_key)
            cds_tag = f'CDS-{cds_num}' if cds_num else issue_key
            existing_issue = self.jira_client.search_existing_by_cds(cds_num) if cds_num else None
            if existing_issue:
                existing_key = existing_issue.get('key')
                fields = existing_issue.get('fields', {})
                created_issues.append({
                    'key': existing_key,
                    'assignee_name': self.user_names.get(assignee_id, assignee_id),
                    'title': fields.get('summary', build_summary(cds_tag, summary_source)),
                    'link': self.jira_client.build_issue_link(existing_key) if existing_key else source_link,
                })
                continue

            summary = build_summary(cds_tag, summary_source)
            issue_type = self.issue_type_client.generate_issue_type(summary_source)
            try:
                created_key, _ = self.jira_client.create_issue(summary, issue_type, assignee_id)
                _, display_name = self.jira_client.resolve_assignee(assignee_id)
                created_issues.append({
                    'key': created_key,
                    'assignee_name': display_name,
                    'title': summary,
                    'link': self.jira_client.build_issue_link(created_key),
                })
            except Exception as error:
                print(f'[WARN] No se pudo crear issue para {issue_key}: {error}', file=sys.stderr)
                continue
            time.sleep(0.2)
        self.repository.save_created_issues(output_path, created_issues)
        return created_issues
