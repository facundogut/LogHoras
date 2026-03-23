from datetime import datetime

import requests

from loghoras.application.tracker_service import JiraTrackerService
from loghoras.infrastructure.jira_client import JiraClient
from loghoras.infrastructure.log_repository import MonthlyLogRepository
from loghoras.shared.config import load_tracker_config


def main() -> None:
    config = load_tracker_config()
    service = JiraTrackerService(config, JiraClient(config), MonthlyLogRepository(config))
    now = datetime.now().astimezone()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        novedades = service.update_log_entries(now)
        novedades_path = service.repository.save_novedades(novedades)
        print(f'OK - Logs actualizados en {config.output_dir} (mes actual y/o meses previos si hubo rollover).')
        print(f'OK - Novedades de esta corrida en:\n  {novedades_path}')
    except requests.exceptions.Timeout:
        print('ERROR: Timeout al consultar JIRA (aumentá REQUEST_TIMEOUT si es recurrente).')
    except requests.exceptions.SSLError as error:
        print(f'ERROR SSL: {error} (usá VERIFY_SSL=True con certificados válidos).')
    except Exception as error:
        print(f'ERROR inesperado: {error}')


if __name__ == '__main__':
    main()
