import os
import warnings
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

from dotenv import load_dotenv
from urllib3.exceptions import InsecureRequestWarning


def _load_env() -> None:
    dotenv_path = Path('../boveda/config.env').resolve()
    if dotenv_path.exists():
        load_dotenv(dotenv_path)


@dataclass(frozen=True)
class TrackerConfig:
    jira_url: str = 'https://jira.nbch.com.ar'
    jira_token: str | None = None
    output_dir: Path = field(default_factory=lambda: Path.cwd() / 'resultado')
    novedades_filename: str = 'novedades.json'
    work_start: time = time(9, 0, 0)
    work_end: time = time(18, 0, 0)
    business_days: set[int] = field(default_factory=lambda: {0, 1, 2, 3, 4})
    holidays: set[str] = field(default_factory=set)
    verify_ssl: bool = False
    request_timeout: int = 60
    project_keys: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=lambda: [
        'c00urruttl', 'c00andreet', 'c00moreitv', 'c00schencl',
        'c00zacheom', 'c00gentaem', 'c00zapicof', 'c00alvarg',
        'c00gutiefa', 'c00vivesma', 'c00pererac', 'c00saucecl',
        'c00aloyfed', 'c00britomj',
    ])
    status_target: list[str] = field(default_factory=lambda: ['DES - DOING', 'DISEÑO - DOING'])
    fields: str = 'summary,status,assignee,created,updated,assignee.name,assignee.displayName'

    @property
    def headers(self) -> dict[str, str]:
        return {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.jira_token}',
        }

    @property
    def novedades_path(self) -> Path:
        return self.output_dir / self.novedades_filename


def load_tracker_config() -> TrackerConfig:
    _load_env()
    warnings.simplefilter('ignore', InsecureRequestWarning)
    return TrackerConfig(jira_token=os.getenv('TOKEN_JIRA_CDS'))
