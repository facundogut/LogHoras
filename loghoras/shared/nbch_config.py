import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from urllib3.exceptions import InsecureRequestWarning


def _load_env() -> None:
    dotenv_path = Path('../boveda/config.env').resolve()
    if dotenv_path.exists():
        load_dotenv(dotenv_path)


@dataclass(frozen=True)
class NbchSyncConfig:
    jira_url: str = 'https://topsystems.atlassian.net'
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project: str = 'NBCH'
    ssl_no_verify: bool = True
    sai_apikey: str | None = None
    base_dir: Path = field(default_factory=Path.cwd)
    default_input: str = 'resultado/novedades.json'
    default_output: str = 'salidaTeams/creados.json'
    request_timeout: int = 60
    ai_timeout: int = 10
    reporter_account_id: str = '615ca1fb9cdb9300727eba64'
    project_field_id: str = '26148'
    account_field_id: str = '152'
    module_field_id: str = '26254'
    tempo_account_id: str = '152'
    default_issue_type_id: str = '10024'
    cds_user_to_cloud_account: dict[str, str] = field(default_factory=lambda: {
        'c00andreet': '557058:65b58152-1002-4e72-9428-7e0a00961d6f',
        'c00schencl': '62d9676996f239ca6ae866c0',
        'c00gentaem': '62708e8666ad530069d2ba00',
        'c00urruttl': '5e5e93a04d2a000c9116128b',
        'c00gutiefa': '712020:f48402a5-39e1-4ba5-9e89-36f486692c8a',
        'c00moreitv': '628d21e8c65b7200696186ca',
        'c00saucecl': '712020:f30fc2d1-bd6e-49a0-8dd9-468c9385118f',
        'c00alvarg': '627ea6e266eb5800698101fa',
        'c00zapicof': '627ea6e266eb5800698101fa',
        'c00pererac': '712020:61d354a8-440c-4860-8bfe-92e0d102d5f7',
    })
    cds_user_to_name: dict[str, str] = field(default_factory=lambda: {
        'c00andreet': 'Enzo Andreetti',
        'c00schencl': 'Lautaro Schenck',
        'c00gentaem': 'Emiliano Genta',
        'c00urruttl': 'Lucía Urruty',
        'c00gutiefa': 'Facundo Gutiérrez',
        'c00moreitv': 'Valentina Moreira',
        'c00saucecl': 'Clara Saucedo',
        'c00alvarg': 'Gastón Álvarez',
        'c00zapicof': 'Florencia Zapico',
        'c00pererac': 'Cristhian Perera',
    })

    @property
    def auth(self) -> tuple[str | None, str | None]:
        return self.jira_email, self.jira_api_token

    @property
    def headers(self) -> dict[str, str]:
        return {'Accept': 'application/json', 'Content-Type': 'application/json'}

    @property
    def input_path(self) -> Path:
        return self.base_dir / self.default_input

    @property
    def output_path(self) -> Path:
        return self.base_dir / self.default_output


def load_nbch_config() -> NbchSyncConfig:
    _load_env()
    warnings.simplefilter('ignore', InsecureRequestWarning)
    return NbchSyncConfig(
        jira_email=os.getenv('USUARIO_JIRA_NBCH'),
        jira_api_token=os.getenv('TOKEN_JIRA_NBCH'),
        jira_project=os.getenv('JIRA_PROJECT', 'NBCH'),
        sai_apikey=os.getenv('API_KEY_SAI'),
    )
