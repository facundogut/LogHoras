from __future__ import annotations

import requests

from loghoras.shared.topaz_config import TopazSyncConfig


class IssueTypeClient:
    def __init__(self, config: TopazSyncConfig):
        self.config = config
        self.url = 'https://sai-library.saiapplications.com/api/templates/68dd7d6c8149437f967307a0/execute'

    def generate_issue_type(self, summary_source: str) -> str:
        headers = {
            'accept': '*/*',
            'Content-Type': 'application/json',
            'X-Api-Key': self.config.sai_apikey or '',
        }
        payload = {'inputs': {'input': summary_source}, 'chatMessages': []}
        try:
            response = requests.post(
                self.url,
                json=payload,
                headers=headers,
                verify=not self.config.ssl_no_verify,
                timeout=self.config.ai_timeout,
            )
            response.raise_for_status()
            return response.text
        except Exception:
            return self.config.default_issue_type_id
