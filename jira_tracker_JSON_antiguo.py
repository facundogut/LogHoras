import os
import json
import requests
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
import warnings
from urllib3.exceptions import InsecureRequestWarning

# Cargar variables de entorno
dotenv_path = os.path.abspath("../boveda/config.env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Suprimir advertencias de solicitudes inseguras
warnings.simplefilter('ignore', InsecureRequestWarning)

# Configuración
JIRA_TOKEN = os.getenv("TOKEN_JIRA_CDS")
JIRA_URL = "https://jira.nbch.com.ar"
JIRA_HEADERS = {
    "Authorization": f"Bearer {JIRA_TOKEN}",
    "Content-Type": "application/json"
}
BASE_DIR = os.getcwd()
#RESULT_DIR = BASE_DIR
RESULT_DIR = os.path.join(BASE_DIR, "resultadoprueba")
WORK_START = time(9, 0)
WORK_END = time(18, 0)
BUSINESS_DAYS = {0,1,2,3,4}  # lun-vie

def get_transition_times(issue_key):
    url = f"{JIRA_URL}/rest/api/2/issue/{issue_key}?expand=changelog"
    response = requests.get(url, headers=JIRA_HEADERS, verify=False)
    if response.status_code != 200:
        print(f"Error al obtener changelog de {issue_key}: {response.status_code}")
        return None, None

    data = response.json()
    changelog = data.get("changelog", {}).get("histories", [])
    transitions = []

    for history in sorted(changelog, key=lambda h: h["created"]):
        for item in history.get("items", []):
            if item.get("field") == "status":
                from_status = item.get("fromString")
                to_status = item.get("toString")
                timestamp = history.get("created")

                transitions.append((from_status, to_status, timestamp))

    last_entered = None
    still_in = False

    for i, (from_status, to_status, timestamp) in enumerate(transitions):
        if to_status == "DES - DOING":
            last_entered = timestamp
            still_in = True
            # Revisar si hay una salida posterior
            for j in range(i+1, len(transitions)):
                if transitions[j][0] == "DES - DOING":
                    still_in = False
                    break
            if still_in:
                break

    last_exited = None
    for from_status, to_status, timestamp in transitions:
        if from_status == "DES - DOING":
            last_exited = timestamp

    return last_entered, last_exited

def get_current_issues():
    jql_query = '(labels != ATDATOS OR labels IS EMPTY) AND status = "DES - DOING" AND assignee IN (c00urruttl, c00andreet, c00moreitv, c00schencl, c00zacheom, c00gentaem, c00zapicof, c00alvarg, c00gutiefa, c00vivesma, c00pererac, c00saucecl)'
    url = f"{JIRA_URL}/rest/api/2/search"
    params = {
        "jql": jql_query,
        "fields": "summary,status,assignee,created,updated"
    }
    response = requests.get(url, headers=JIRA_HEADERS, params=params, verify=False)
    if response.status_code == 200:
        return response.json().get("issues", [])
    else:
        print(f"Error al consultar JIRA: {response.status_code} - {response.text}")
        return []

def load_existing_log():
    now = datetime.now()
    file_name = f"jira_log_{now.strftime('%Y-%m')}.json"
    file_path = os.path.join(RESULT_DIR, file_name)
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Error leyendo log existente: {e}")
        return []

def is_business_day(dt):
    return dt.weekday() in BUSINESS_DAYS

def calculate_working_hours(start, end):
    total = timedelta()
    current = start
    while current.date() <= end.date():
        if is_business_day(current):
            ws = datetime.combine(current.date(), WORK_START)
            we = datetime.combine(current.date(), WORK_END)
            if current.date() == start.date():
                ws = max(ws, start)
            if current.date() == end.date():
                we = min(we, end)
            if ws < we:
                total += we - ws
        current += timedelta(days=1)
    return round(total.total_seconds()/3600, 2)

def process_current_issues(current_issues, open_entries, now):
    updated_log = []
    for issue in current_issues:
        issue_id = issue["key"]
        summary = issue["fields"]["summary"]
        assignee = issue["fields"]["assignee"]["displayName"] if issue["fields"]["assignee"] else "Unassigned"
        key = (issue_id, assignee)

        if key in open_entries:
            updated_log.append(open_entries[key])
        else:
            entered, _ = get_transition_times(issue_id)
            if entered:
                start_time = entered
            else:
                start_time = datetime.combine(now.date(), WORK_START).isoformat() if now.time() < WORK_START else now.isoformat()

            updated_log.append({
                "issue_id": issue_id,
                "summary": summary,
                "assignee": assignee,
                "start_time": start_time,
                "end_time": "",
                "duration_hours": 0
            })

    return updated_log

def parse_iso_datetime(dt_str):
     if dt_str and dt_str[-5] in ['+', '-'] and dt_str[-3] != ':':
      dt_str = dt_str[:-5] + dt_str[-5:-2] + ':' + dt_str[-2:]
     return datetime.fromisoformat(dt_str).replace(tzinfo=None)


def close_inactive_issues(existing_log, current_keys, now):
    closed_entries = []
    for entry in existing_log:
        key = (entry["issue_id"], entry["assignee"])
        if entry["end_time"]:
            closed_entries.append(entry)
        elif key not in current_keys:
            start = parse_iso_datetime(entry["start_time"])
            _, exited = get_transition_times(entry["issue_id"])
            if exited:
                end = parse_iso_datetime(exited)
            else:
                end = datetime.combine(now.date(), WORK_END) if now.time() > WORK_END else now
            duration = calculate_working_hours(start, end)
            entry["end_time"] = end.isoformat()
            entry["duration_hours"] = duration
            closed_entries.append(entry)
    return closed_entries

def save_log(log_entries):
    os.makedirs(RESULT_DIR, exist_ok=True)
    now = datetime.now()
    file_name = f"jira_log_{now.strftime('%Y-%m')}.json"
    file_path = os.path.join(RESULT_DIR, file_name)

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                existing_entries = json.load(f)
        except Exception:
            existing_entries = []
    else:
        existing_entries = []

    # Crear un set de claves únicas para evitar duplicados exactos
    def entry_key(entry):
        return (entry["issue_id"], entry["assignee"], entry["start_time"])

    existing_keys = {entry_key(e): e for e in existing_entries}
    
    for new_entry in log_entries:
        key = entry_key(new_entry)
        if key in existing_keys:
            # Si ya existe, actualizamos solo si está abierta
            if not existing_keys[key]["end_time"] and new_entry["end_time"]:
                existing_keys[key].update(new_entry)
        else:
            # Si no existe, la agregamos
            existing_keys[key] = new_entry

    # Guardar todos los valores únicos
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(list(existing_keys.values()), f, indent=2, ensure_ascii=False)


def get_issue_keys(issues):
    return set(
        (issue["key"], issue["fields"]["assignee"]["displayName"] if issue["fields"]["assignee"] else "Unassigned")
        for issue in issues
    )

def main():
    existing_log = load_existing_log()
    current_issues = get_current_issues()
    now = datetime.now()

    open_entries = {
        (e["issue_id"], e["assignee"]): e
        for e in existing_log if not e["end_time"]
    }

    current_keys = get_issue_keys(current_issues)

    updated_log = process_current_issues(current_issues, open_entries, now)
    closed_entries = close_inactive_issues(existing_log, current_keys, now)

    updated_keys = {(entry["issue_id"], entry["assignee"]) for entry in updated_log}
    filtered_closed_entries = [entry for entry in closed_entries if (entry["issue_id"], entry["assignee"]) not in updated_keys]
    updated_log.extend(filtered_closed_entries)

    save_log(updated_log)

if __name__ == "__main__":
    main()
