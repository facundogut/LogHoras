import os
import sys
import json
import time
import argparse
import re
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
import warnings
from urllib3.exceptions import InsecureRequestWarning
import requests

# Cargar variables de entorno
dotenv_path = os.path.abspath("../boveda/config.env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Suprimir advertencias de solicitudes inseguras
warnings.simplefilter('ignore', InsecureRequestWarning)

JIRA_URL = "https://topsystems.atlassian.net"
JIRA_EMAIL     = os.getenv("USUARIO_JIRA_NBCH")
JIRA_API_TOKEN = os.getenv("TOKEN_JIRA_NBCH")
JIRA_PROJECT   = os.getenv("JIRA_PROJECT", "NBCH")
SSL_NO_VERIFY  = True
SAI_APIKEY = os.getenv("API_KEY_SAI")

BASE_DIR = os.getcwd()

if not (JIRA_URL and JIRA_EMAIL and JIRA_API_TOKEN):
    print("Faltan variables de entorno: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN", file=sys.stderr)

AUTH  = (JIRA_EMAIL, JIRA_API_TOKEN)
HEADS = {"Accept": "application/json", "Content-Type": "application/json"}

# ========= Mappings (completa los accountId si ya los tenés) =========
CDS_USER_TO_CLOUD_ACCOUNT = {
    "c00andreet":"557058:65b58152-1002-4e72-9428-7e0a00961d6f",
    "c00schencl":"62d9676996f239ca6ae866c0",
    "c00gentaem":"62708e8666ad530069d2ba00",
    "c00urruttl":"5e5e93a04d2a000c9116128b",
    "c00gutiefa":"712020:f48402a5-39e1-4ba5-9e89-36f486692c8a",
    "c00moreitv":"628d21e8c65b7200696186ca",
    "c00saucecl":"712020:f30fc2d1-bd6e-49a0-8dd9-468c9385118f",
    "c00alvarg":"627ea6e266eb5800698101fa",
    "c00zapicof":"627ea6e266eb5800698101fa",
    "c00pererac":"712020:61d354a8-440c-4860-8bfe-92e0d102d5f7",
}
CDS_USER_TO_NAME = {
    "c00andreet": "Enzo Andreetti",
    "c00schencl": "Lautaro Schenck",
    "c00gentaem": "Emiliano Genta",
    "c00urruttl": "Lucía Urruty",
    "c00gutiefa": "Facundo Gutiérrez",
    "c00moreitv": "Valentina Moreira",
    "c00saucecl": "Clara Saucedo",
    "c00alvarg":  "Gastón Álvarez",
    "c00zapicof": "Florencia Zapico",
    "c00pererac": "Cristhian Perera",
}

# ========= HTTP helpers =========

def _req_with_backoff(method: str, url: str, **kwargs) -> requests.Response:
    for intento in range(4):
        r = requests.request(
            method,
            url,
            headers=HEADS,
            auth=AUTH,
            verify=not SSL_NO_VERIFY,
            timeout=60,
            **kwargs,
        )
        # rate limit
        if r.status_code == 429:
            time.sleep(2 ** intento)
            continue
        return r
    return r  # último intento

def jira_get_json(path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    url = f"{JIRA_URL}{path}"
    r = _req_with_backoff("GET", url, params=params)
    if r.status_code >= 400:
        # tratar de mostrar mensaje json si existe
        try:
            details = r.json()
        except Exception:
            details = r.text
        raise RuntimeError(f"GET {path} fallo: {r.status_code} -> {details}")
    return r.json()

def jira_post_json(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{JIRA_URL}{path}"
    r = _req_with_backoff("POST", url, data=json.dumps(payload))
    if r.status_code >= 400:
        try:
            details = r.json()
        except Exception:
            details = r.text
        raise RuntimeError(f"POST {path} fallo: {r.status_code} -> {details}")
    return r.json()

def build_issue_link(key: str) -> str:
    return f"{JIRA_URL}/browse/{key}"

# ========= Domain helpers =========

def extract_cds_number(issue_key: str) -> Optional[str]:
    """
    Obtiene el número '1234' desde 'CDS-1234' o variantes con/ sin espacios.
    """
    if not issue_key:
        return None
    m = re.search(r"CDS\s*-\s*(\d+)", issue_key, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"CDS\s*(\d+)", issue_key, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return None

def search_existing_by_cds(cds_num: str) -> Optional[Dict[str, Any]]:
    """
    Usa el endpoint NUEVO /rest/api/3/search/jql para evitar 410.
    Busca issues NBCH cuyo summary contenga el CDS.
    """
    jql = (
        f'project = {JIRA_PROJECT} AND ('
        f'summary ~ "\\"CDS {cds_num}\\"" OR '
        f'summary ~ "\\"CDS-{cds_num}\\"" OR '
        f'summary ~ "\\"CDS -{cds_num}\\"" OR '
        f'summary ~ "\\"CDS- {cds_num}\\"")'
    )

    # Nuevo endpoint (POST recomendado). Campos acotados.
    body = {
        "jql": jql,
        "fields": ["key", "summary", "assignee"],
        "maxResults": 5
    }

    # Llamada principal
    try:
        res = jira_post_json("/rest/api/3/search/jql", body)
    except RuntimeError as e:
        # Por compatibilidad: algunos tenants aún aceptan GET /search/jql
        # o POST /search; si falla, probamos fallback 1: GET /search/jql
        if "410" in str(e):
            # 410 ya indica endpoint viejo removido; no vale la pena intentar /search
            raise
        try:
            res = jira_get_json("/rest/api/3/search/jql", params={"jql": jql, "fields": "key,summary,assignee", "maxResults": 5})
        except Exception:
            raise

    issues = res.get("issues", [])
    return issues[0] if issues else None

def resolve_assignee(assignee_id: str) -> Tuple[Optional[str], str]:
    """
    Devuelve (accountId, display_name) para asignación. Usa mapping y, si no está, intenta /user/search.
    """
    display = CDS_USER_TO_NAME.get(assignee_id, assignee_id)
    if assignee_id in CDS_USER_TO_CLOUD_ACCOUNT:
        return CDS_USER_TO_CLOUD_ACCOUNT[assignee_id], display

    # Fallback: intentar buscar por cadena (puede matchear por nombre, email, etc.)
    try:
        users = jira_get_json("/rest/api/3/user/search", params={"query": assignee_id})
        if users:
            return users[0].get("accountId"), users[0].get("displayName", display)
    except Exception:
        pass
    return None, display  # sin asignar si no se puede

def make_issue_payload(project_key: str,
                       summary: str,
                       issueType: str,
                       assignee_account: Optional[str]) -> Dict[str, Any]:
    fields = {
        "project": {"key": project_key},
        "summary": summary,
        "issuetype": {"id": issueType},
        "reporter": {"accountId": "615ca1fb9cdb9300727eba64"}, #Informador
        "customfield_11203": {"id": "26148"}, #Proyecto
        "customfield_11900": {"id": "152"}, #Account
        "customfield_10025": {"id": "26254"}, #Modulo
        "io.tempo.jira__account":"152", #Account Tempo
        "description": {
            "type": "doc",
            "version": 1,
            "content": [
                {"type": "paragraph",
                 "content": [{"type": "text", "text": "Asignación de tareas según disponibilidad horaria del equipo"}]}
            ],
        },
        # "labels": ["cds-auto"],  # opcional
    }
    if assignee_account:
        fields["assignee"] = {"accountId": assignee_account}
    return {"fields": fields}

def create_issue_nbch(summary: str, issueType: str, assignee_id: str) -> Tuple[str, str]:
    """
    Crea la issue en NBCH. Retorna (key, self_url)
    """
    accountId, _ = resolve_assignee(assignee_id)
    payload = make_issue_payload(JIRA_PROJECT, summary, issueType, accountId)
    res = jira_post_json("/rest/api/3/issue", payload)
    return res["key"], res.get("self", "")

def generate_issue_type(summary_src: str) -> str:
    url = "https://sai-library.saiapplications.com/api/templates/68dd7d6c8149437f967307a0/execute"
    headers = {
        "accept": "*/*",
        "Content-Type": "application/json",
        "X-Api-Key": SAI_APIKEY
    }
    data = {
        "inputs": {
            "input": summary_src
        },
        "chatMessages": []
    }

    try:
        response = requests.post(
            url,
            json=data,
            headers=headers,
            verify=False,
            timeout=10
        )
        response.raise_for_status()

        return response.text

    except Exception:
        return "10024"

# ========= Flujo principal =========

def load_novedades(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("novedades.json debe ser una lista de objetos.")
    for i, n in enumerate(data, 1):
        for field in ("issue_key", "assignee_id", "summary", "link"):
            if field not in n:
                raise ValueError(f"Elemento #{i} no tiene campo requerido '{field}'.")
    return data

def main(input_path: str, output_path: str):
    novedades = load_novedades(input_path)
    creados: List[Dict[str, Any]] = []

    if novedades:
        for n in novedades:
            cds_key = str(n["issue_key"]).strip()           # p.ej. "CDS-6849"
            assignee_id = str(n["assignee_id"]).strip()
            summary_src = str(n["summary"]).strip()
            src_link = str(n["link"]).strip()

            cds_num = extract_cds_number(cds_key)
            cds_tag = f"CDS-{cds_num}" if cds_num else cds_key

            # 1) Dedupe por CDS en summary (nuevo endpoint jql)
            ya = search_existing_by_cds(cds_num) if cds_num else None
            if ya:
                # Ya existe: agregar a 'creados' con datos del existente y NO crear nada
                key_exist = ya.get("key")
                fields_exist = ya.get("fields", {})
                title_exist = fields_exist.get("summary", f"[{cds_tag}] {summary_src}")
                assignee_name_log = CDS_USER_TO_NAME.get(assignee_id, assignee_id)

                creados.append({
                    "key": key_exist,
                    "assignee_name": assignee_name_log,
                    "title": title_exist,
                    "link": build_issue_link(key_exist) if key_exist else src_link
                })
                continue

            # 2) Summary estilo “versión anterior”
            summary = f"[{cds_tag}] {summary_src}" if cds_tag else summary_src

            # 3) Determina el issue Type
            issueType = generate_issue_type(summary_src)

            # 4) Crear issue
            try:
                key, _ = create_issue_nbch(summary, issueType, assignee_id)
                _, display = resolve_assignee(assignee_id)
                creados.append({
                    "key": key,
                    "assignee_name": display,
                    "title": summary,
                    "link": build_issue_link(key),
                })
            except Exception as e:
                print(f"[WARN] No se pudo crear issue para {cds_key}: {e}", file=sys.stderr)
                continue

            time.sleep(0.2)  # backoff suave

    # 5) Guardar salida
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(creados, f, ensure_ascii=False, indent=2)

    print(f"Listo. Se crearon {len(creados)} issues. Salida: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crea issues NBCH desde novedades.json evitando duplicados por CDS.")
    parser.add_argument("--input", "-i", default=os.path.join(BASE_DIR, "resultado/novedades.json"), help="Ruta al archivo novedades.json")
    parser.add_argument("--output", "-o", default=os.path.join(BASE_DIR, "salidaTeams/creados.json"), help="Ruta de salida para creados.json")
    args = parser.parse_args()
    main(args.input, args.output)
