from datetime import datetime
import sys
import traceback

import requests

from loghoras.application.tracker_service import JiraTrackerService
from loghoras.infrastructure.nbch_jira_client import NbchJiraClient
from loghoras.infrastructure.log_repository import MonthlyLogRepository
from loghoras.shared.config import load_tracker_config


def _print_exception_details(context: str, error: Exception) -> None:
    print(f'{context}: {error}', file=sys.stderr)
    traceback.print_exc()


def main() -> int:
    config = load_tracker_config()
    service = JiraTrackerService(config, NbchJiraClient(config), MonthlyLogRepository(config))
    now = datetime.now().astimezone()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        log_path = service.update_log_entries(now)
        print(f'OK - Registro de issues activas actualizado en: {log_path}')
        return 0
    except requests.exceptions.Timeout as error:
        _print_exception_details('ERROR: Timeout al consultar JIRA (aumentá REQUEST_TIMEOUT si es recurrente)', error)
        return 1
    except requests.exceptions.SSLError as error:
        _print_exception_details('ERROR SSL (usá VERIFY_SSL=True con certificados válidos)', error)
        return 1
    except Exception as error:
        _print_exception_details('ERROR inesperado', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
