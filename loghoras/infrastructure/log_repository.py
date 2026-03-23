from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loghoras.domain.time_tracking import month_filename
from loghoras.shared.config import TrackerConfig


class MonthlyLogRepository:
    def __init__(self, config: TrackerConfig):
        self.config = config

    def month_log_path(self, dt: datetime) -> Path:
        return Path(month_filename(dt, self.config))

    def ensure_log_file_exists(self, dt: datetime) -> None:
        path = self.month_log_path(dt)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text('{}', encoding='utf-8')

    def load_month_log(self, dt: datetime) -> dict[str, Any]:
        self.ensure_log_file_exists(dt)
        path = self.month_log_path(dt)
        try:
            return json.loads(path.read_text(encoding='utf-8')) or {}
        except Exception:
            path.write_text('{}', encoding='utf-8')
            return {}

    def save_month_log(self, dt: datetime, data: dict[str, Any]) -> None:
        self.ensure_log_file_exists(dt)
        path = self.month_log_path(dt)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def save_novedades(self, novedades: list[dict[str, Any]]) -> str:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.novedades_path
        with path.open('w', encoding='utf-8') as handle:
            json.dump(novedades, handle, ensure_ascii=False, indent=2)
            handle.flush()
        return str(path.resolve())
