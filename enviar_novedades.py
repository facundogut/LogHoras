import argparse
import sys
import traceback

from loghoras.application.novedades_service import NovedadesSyncService
from loghoras.infrastructure.issue_type_client import IssueTypeClient
from loghoras.infrastructure.topaz_jira_client import TopazJiraClient
from loghoras.infrastructure.novedades_repository import NovedadesRepository
from loghoras.shared.topaz_config import load_topaz_config


def _print_exception_details(context: str, error: Exception) -> None:
    print(f'{context}: {error}', file=sys.stderr)
    traceback.print_exc()


def main(input_path: str, output_path: str) -> int:
    config = load_topaz_config()
    if not (config.jira_url and config.jira_email and config.jira_api_token):
        print('Faltan variables de entorno para Jira TOPAZ: USUARIO_JIRA_NBCH, TOKEN_JIRA_NBCH y/o JIRA_PROJECT', file=sys.stderr)
    service = NovedadesSyncService(
        repository=NovedadesRepository(),
        jira_client=TopazJiraClient(config),
        issue_type_client=IssueTypeClient(config),
        user_names=config.cds_user_to_name,
    )
    try:
        created_issues = service.sync(input_path, output_path)
        print(f'Listo. Se crearon {len(created_issues)} issues. Salida: {output_path}')
        return 0
    except Exception as error:
        _print_exception_details('ERROR al enviar novedades', error)
        return 1


if __name__ == '__main__':
    config = load_topaz_config()
    parser = argparse.ArgumentParser(description='Crea issues en Jira TOPAZ (proyecto NBCH) desde novedades.json evitando duplicados por CDS.')
    parser.add_argument('--input', '-i', default=str(config.input_path), help='Ruta al archivo novedades.json')
    parser.add_argument('--output', '-o', default=str(config.output_path), help='Ruta de salida para creados.json')
    args = parser.parse_args()
    raise SystemExit(main(args.input, args.output))
