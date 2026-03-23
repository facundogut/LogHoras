from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loghoras.domain.novedades import validate_novedades


class NovedadesRepository:
    def load_novedades(self, path: str) -> list[dict[str, Any]]:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return validate_novedades(data)

    def save_created_issues(self, path: str, created_issues: list[dict[str, Any]]) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open('w', encoding='utf-8') as handle:
            json.dump(created_issues, handle, ensure_ascii=False, indent=2)
