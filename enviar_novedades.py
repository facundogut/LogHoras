import argparse
import sys

from loghoras.application.novedades_service import NovedadesSyncService
from loghoras.infrastructure.issue_type_client import IssueTypeClient
from loghoras.infrastructure.nbch_jira_client import NbchJiraClient
from loghoras.infrastructure.novedades_repository import NovedadesRepository
from loghoras.shared.nbch_config import load_nbch_config


def main(input_path: str, output_path: str) -> None:
    config = load_nbch_config()
    if not (config.jira_url and config.jira_email and config.jira_api_token):
        print('Faltan variables de entorno: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN', file=sys.stderr)
    service = NovedadesSyncService(
        repository=NovedadesRepository(),
        jira_client=NbchJiraClient(config),
        issue_type_client=IssueTypeClient(config),
        user_names=config.cds_user_to_name,
    )
    created_issues = service.sync(input_path, output_path)
    print(f'Listo. Se crearon {len(created_issues)} issues. Salida: {output_path}')


if __name__ == '__main__':
    config = load_nbch_config()
    parser = argparse.ArgumentParser(description='Crea issues NBCH desde novedades.json evitando duplicados por CDS.')
    parser.add_argument('--input', '-i', default=str(config.input_path), help='Ruta al archivo novedades.json')
    parser.add_argument('--output', '-o', default=str(config.output_path), help='Ruta de salida para creados.json')
    args = parser.parse_args()
    main(args.input, args.output)
