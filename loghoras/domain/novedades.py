from __future__ import annotations

import re
from typing import Any


REQUIRED_NOVEDAD_FIELDS = ('issue_key', 'assignee_id', 'summary', 'link')


def extract_cds_number(issue_key: str) -> str | None:
    if not issue_key:
        return None
    match = re.search(r'CDS\s*-\s*(\d+)', issue_key, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'CDS\s*(\d+)', issue_key, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def validate_novedades(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        raise ValueError('novedades.json debe ser una lista de objetos.')
    for index, item in enumerate(data, 1):
        for field in REQUIRED_NOVEDAD_FIELDS:
            if field not in item:
                raise ValueError(f"Elemento #{index} no tiene campo requerido '{field}'.")
    return data


def build_summary(cds_tag: str | None, summary_source: str) -> str:
    return f'[{cds_tag}] {summary_source}' if cds_tag else summary_source
