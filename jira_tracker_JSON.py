import os
import json
import requests
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv
import warnings
from urllib3.exceptions import InsecureRequestWarning

# =========================
# ======= CONFIG ==========
# =========================
# Cargar variables de entorno
dotenv_path = os.path.abspath("../boveda/config.env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

# Suprimir advertencias de solicitudes inseguras
warnings.simplefilter('ignore', InsecureRequestWarning)

JIRA_URL = "https://jira.nbch.com.ar"
JIRA_TOKEN = os.getenv("TOKEN_JIRA_CDS")

BASE_DIR = os.getcwd()

OUTPUT_DIR = os.path.join(BASE_DIR, "resultado")
NOVEDADES_FILENAME = "novedades.json"

WORK_START = time(9, 0, 0)   # Inicio jornada
WORK_END   = time(18, 0, 0)  # Fin jornada

BUSINESS_DAYS = {0, 1, 2, 3, 4}  # lun-vie

# (Opcional) feriados YYYY-MM-DD;
HOLIDAYS = set([
    # "2025-01-01",
])

VERIFY_SSL = False
REQUEST_TIMEOUT = 60        # segundos

PROJECT_KEYS = []  # opcional; si no querés filtrar por proyecto, dejalo como [] y no se agrega
ASSIGNEES = [
    "c00urruttl","c00andreet","c00moreitv","c00schencl",
    "c00zacheom","c00gentaem","c00zapicof","c00alvarg",
    "c00gutiefa","c00vivesma","c00pererac","c00saucecl",
    "c00aloyfed", "c00britomj"
]
STATUS_TARGET = ["DES - DOING", "DISEÑO - DOING"]

def jql_quote(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'

def build_status_in_clause(statuses: list[str]) -> str:
    return ", ".join(jql_quote(s) for s in statuses)

def build_scope_clause() -> str:
    parts = []
    # tu filtro de labels original
    parts.append('(labels != ATDATOS OR labels IS EMPTY)')
    # proyecto (si definiste PROJECT_KEYS)
    if PROJECT_KEYS:
        parts.append('project in ({})'.format(', '.join(PROJECT_KEYS)))
    # assignees (tu lista)
    parts.append('assignee in ({})'.format(', '.join(ASSIGNEES)))
    return ' AND '.join(parts)

SCOPE = build_scope_clause()

FIELDS = "summary,status,assignee,created,updated,assignee.name,assignee.displayName"

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {JIRA_TOKEN}",
}


# =========================
# ===== Utilidades tz =====
# =========================
def parse_jira_datetime(s: str) -> datetime:
    """
    JIRA suele devolver ISO con TZ '±HHmm'. Python fromisoformat requiere '±HH:MM'.
    Normalizamos y devolvemos 'aware'.
    """
    if not s:
        return None
    if len(s) >= 5 and (s[-5] in ['+', '-']) and s[-3:].isdigit():
        s = s[:-5] + s[-5:-2] + ":" + s[-2:]
    dt = datetime.fromisoformat(s)
    return dt  # aware si venía con tz

def build_issue_link(issue_key: str) -> str:
    # Soporta Jira Server con context path
    base = JIRA_URL.rstrip("/")
    return f"{base}/browse/{issue_key}"

def save_novedades(novedades: list) -> str:
    """
    Guarda las novedades de esta corrida como una lista JSON:
    [{issue_key, assignee_id, summary, link}, ...]
    """
    path = os.path.abspath(os.path.join(OUTPUT_DIR, NOVEDADES_FILENAME))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(novedades, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    return path


# =========================
# == Horas hábiles (L-V) ==
# =========================
def is_business_day(dt_or_date) -> bool:
    d = dt_or_date
    if isinstance(d, datetime):
        d = d.date()
    if d.strftime("%Y-%m-%d") in HOLIDAYS:
        return False
    return d.weekday() in BUSINESS_DAYS


def clamp_day_interval(start_dt: datetime, end_dt: datetime, day: date) -> timedelta:
    """Tramo de [start_dt, end_dt] que cae en 'day' y dentro de [WORK_START, WORK_END]."""
    ws = datetime.combine(day, WORK_START, tzinfo=start_dt.tzinfo)
    we = datetime.combine(day, WORK_END, tzinfo=start_dt.tzinfo)
    seg_start = max(start_dt, ws)
    seg_end = min(end_dt, we)
    return max(seg_end - seg_start, timedelta(0))


def calculate_working_hours(start_dt: datetime, end_dt: datetime) -> float:
    """Suma horas hábiles entre start_dt y end_dt (aware). Excluye fines de semana y feriados."""
    if not start_dt or not end_dt or end_dt <= start_dt:
        return 0.0
    total = timedelta(0)
    cur_day = start_dt.date()
    last_day = end_dt.date()
    while cur_day <= last_day:
        if is_business_day(cur_day):
            total += clamp_day_interval(start_dt, end_dt, cur_day)
        cur_day += timedelta(days=1)
    return round(total.total_seconds() / 3600.0, 2)


# =========================
# == Fechas por mes =======
# =========================
def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def month_filename(dt: datetime) -> str:
    return os.path.join(OUTPUT_DIR, f"jira_log_{month_key(dt)}.json")


def first_day_of_month(dt: datetime) -> date:
    return date(dt.year, dt.month, 1)


def last_day_of_month(dt: datetime) -> date:
    if dt.month == 12:
        return date(dt.year, 12, 31)
    first_next = date(dt.year + (dt.month // 12), (dt.month % 12) + 1, 1)
    return first_next - timedelta(days=1)


def next_month(dt: datetime) -> datetime:
    if dt.month == 12:
        return dt.replace(year=dt.year + 1, month=1, day=1)
    return dt.replace(month=dt.month + 1, day=1)


def find_last_business_day_of_month(dt: datetime) -> date:
    d = last_day_of_month(dt)
    while not is_business_day(d):
        d -= timedelta(days=1)
    return d


def find_first_business_day_of_month(dt: datetime) -> date:
    d = first_day_of_month(dt)
    while not is_business_day(d):
        d += timedelta(days=1)
    return d


def last_business_moment_of_month(dt: datetime) -> datetime:
    last_bd = find_last_business_day_of_month(dt)
    # mantener tz
    return datetime.combine(last_bd, WORK_END, tzinfo=dt.tzinfo)


def first_business_moment_of_month(dt: datetime) -> datetime:
    first_bd = find_first_business_day_of_month(dt)
    return datetime.combine(first_bd, WORK_START, tzinfo=dt.tzinfo)


def first_business_moment_of_year_month(year: int, month: int, tzinfo) -> datetime:
    d = date(year, month, 1)
    while not (d.weekday() in BUSINESS_DAYS and d.strftime("%Y-%m-%d") not in HOLIDAYS):
        d += timedelta(days=1)
    return datetime.combine(d, WORK_START, tzinfo=tzinfo)


def last_business_moment_of_year_month(year: int, month: int, tzinfo) -> datetime:
    if month == 12:
        d = date(year, 12, 31)
    else:
        d = date(year + (month // 12), (month % 12) + 1, 1) - timedelta(days=1)
    while not (d.weekday() in BUSINESS_DAYS and d.strftime("%Y-%m-%d") not in HOLIDAYS):
        d -= timedelta(days=1)
    return datetime.combine(d, WORK_END, tzinfo=tzinfo)


# =========================
# == JIRA REST helpers  ===
# =========================
def get_current_issues() -> list:
    """Trae TODOS los issues de la JQL, paginando."""
    url = f"{JIRA_URL}/rest/api/2/search"
    start_at = 0
    all_issues = []
    JQL_DOING = f'{SCOPE} AND status in ({build_status_in_clause(STATUS_TARGET)})'
    while True:
        params = {"jql": JQL_DOING, "fields": FIELDS, "startAt": start_at, "maxResults": 100}
        r = requests.get(url, headers=HEADERS, params=params,
                         timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        if r.status_code != 200:
            raise RuntimeError(f"Error JIRA search: {r.status_code} - {r.text}")
        data = r.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        total = data.get("total", len(issues))
        if start_at + len(issues) >= total:
            break
        start_at += len(issues)
    return all_issues

def get_recently_exited_issues() -> list:
    """
    Trae issues que salieron de STATUS_TARGET recientemente.
    Usamos una ventana amplia (desde startOfMonth(-1)) para cubrir cierres del mes pasado y del actual.
    """
    EXIT_WINDOW = 'AFTER startOfMonth(-1)'
    JQL_RECENT_EXIT = f'{SCOPE} AND status CHANGED FROM in ({build_status_in_clause(STATUS_TARGET)}) {EXIT_WINDOW}'

    jql = JQL_RECENT_EXIT
    url = f"{JIRA_URL}/rest/api/2/search"
    start_at = 0
    all_issues = []
    while True:
        params = {
            "jql": jql,
            "fields": FIELDS,
            "startAt": start_at,
            "maxResults": 100
        }
        r = requests.get(url, headers=HEADERS, params=params,
                         timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        if r.status_code != 200:
            raise RuntimeError(f"Error JIRA search (recent exits): {r.status_code} - {r.text}")
        data = r.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        total = data.get("total", len(issues))
        if start_at + len(issues) >= total:
            break
        start_at += len(issues)
    return all_issues

def get_all_changelog(issue_key: str, issue_id: Optional[str] = None) -> List[Dict]:
    """
    Jira Server:
      1) Intenta /rest/api/2/issue/{key}/changelog (paginado: values/total/maxResults)
      2) Si falla/404, intenta con issue_id
      3) Si sigue sin éxito, cae a ?expand=changelog y usa changelog.histories
    Retorna una lista de histories ordenadas por 'created'.
    """
    def fetch_paged(path_base: str) -> Optional[List[Dict]]:
        start_at = 0
        acc: List[Dict] = []
        while True:
            url = f"{JIRA_URL}/rest/api/2/issue/{path_base}/changelog"
            params = {"startAt": start_at, "maxResults": 100}
            r = requests.get(url, headers=HEADERS, params=params,
                             timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
            if r.status_code == 404:
                return None  # este endpoint no está disponible para esta ruta
            r.raise_for_status()
            data = r.json()
            # Endpoint paginado: usa 'values'
            chunk = data.get("values")
            if chunk is None:
                # si no trae 'values', no es el endpoint paginado
                return None
            acc.extend(chunk)
            total = data.get("total", start_at + len(chunk))
            max_res = data.get("maxResults", 100)
            if start_at + len(chunk) >= total:
                acc.sort(key=lambda h: h.get("created"))
                return acc
            start_at += max_res

    # 1) probar con key
    histories = fetch_paged(issue_key)
    if histories is not None:
        return histories

    # 2) probar con id
    if issue_id:
        histories = fetch_paged(issue_id)
        if histories is not None:
            return histories

    # 3) fallback: expand=changelog (no paginado; usa changelog.histories)
    for path_base in [issue_key, issue_id] if issue_id else [issue_key]:
        if not path_base:
            continue
        url = f"{JIRA_URL}/rest/api/2/issue/{path_base}"
        r = requests.get(url, headers=HEADERS, params={"expand": "changelog"},
                         timeout=REQUEST_TIMEOUT, verify=VERIFY_SSL)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        data = r.json()
        histories = (data.get("changelog", {}) or {}).get("histories", []) or []
        histories.sort(key=lambda h: h.get("created"))
        return histories

    raise RuntimeError("No se pudo obtener el changelog: ni paginado ni via expand=changelog.")


def get_transition_times(issue_key: str) -> tuple[datetime | None, datetime | None]:
    """
    Devuelve (last_entered_or_open_since, last_exited) para STATUS_TARGET.
    - Si está actualmente en STATUS_TARGET y no hay salida posterior, open_since = última entrada.
    - last_exited: última vez que salió de STATUS_TARGET.
    """
    histories = get_all_changelog(issue_key)
    transitions = []
    for h in histories:
        created = parse_jira_datetime(h.get("created"))
        for item in h.get("items", []):
            if item.get("field") == "status":
                transitions.append((item.get("fromString"), item.get("toString"), created))

    last_entered = None
    last_exited = None
    open_since = None

    for i, (frm, to, ts) in enumerate(transitions):
        if to in STATUS_TARGET:
            last_entered = ts
            has_exit = any(t[0] in STATUS_TARGET for t in transitions[i+1:])
            if not has_exit:
                open_since = ts

    for frm, to, ts in transitions:
        if frm in STATUS_TARGET:
            if (last_exited is None) or (ts and ts > last_exited):
                last_exited = ts

    return (open_since or last_entered), last_exited


# =========================
# == Persistencia (JSON) ==
# =========================
def month_log_path(dt: datetime) -> str:
    return month_filename(dt)


def ensure_log_file_exists(dt: datetime) -> None:
    """
    Si el archivo de log del mes NO existe, lo crea con un objeto JSON vacío {}.
    """
    path = month_log_path(dt)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}")  # JSON vacío válido


def load_month_log(dt: datetime) -> Dict[str, Any]:
    """
    Estructura:
    {
      "<issueId>-<assigneeName>": {
          "issue_key": "...",
          "issue_id": "...",
          "assignee_id": "...",
          "assignee_name": "...",
          "summary": "...",
          "entries": [
              {"entered_at": "ISO", "exited_at": "ISO or null", "worked_hours": float}
          ]
      }, ...
    }
    """
    ensure_log_file_exists(dt)  # <-- garantiza creación si no existe
    path = month_log_path(dt)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        # Si hay corrupción, reescribimos vacío para no fallar todo
        with open(path, "w", encoding="utf-8") as f:
            f.write("{}")
        return {}


def save_month_log(dt: datetime, data: Dict[str, Any]) -> None:
    ensure_log_file_exists(dt)
    path = month_log_path(dt)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =========================
# ===== Lógica main  ======
# =========================
def update_log_entries(now: datetime):
    # Cache de logs por mes para leer/escribir múltiples meses si hay rollover
    logs_cache: dict[str, dict] = {}
    novedades_set = set()   # (issue_id, entered_iso, exited_iso or "OPEN")
    novedades = []

    # -------- utilidades de IO / mes ----------
    def get_log_for(dt: datetime) -> dict:
        mk = month_key(dt)
        if mk not in logs_cache:
            logs_cache[mk] = load_month_log(dt)
        return logs_cache[mk]

    def save_all_logs():
        for mk, data in logs_cache.items():
            year, month = map(int, mk.split("-"))
            dt = datetime(year, month, 1, tzinfo=now.tzinfo)
            save_month_log(dt, data)

    # “de aquí para adelante”: recortar todo al inicio hábil del mes actual
    month_start_now = first_business_moment_of_year_month(now.year, now.month, now.tzinfo)

    # buscar una ABIERTA (exited_at=None) de este issue_id en TODO el mes dado
    def find_open_entry_in_month(month_dt: datetime, _issue_id: str):
        # ¡OJO! No tocar logs de meses que no existen aún.
        mk = month_key(month_dt)
        if mk not in logs_cache:
            # sólo cargá si ya existe en disco; si no, no generes archivo vacío
            path = month_filename(month_dt)
            if not os.path.exists(path):
                return None, None, None
            logs_cache[mk] = load_month_log(month_dt)

        log = get_log_for(month_dt)
        for k, item in log.items():
            if item.get("issue_id") != _issue_id:
                continue
            for e in item.get("entries", []):
                if e.get("exited_at") is None:
                    return k, item, e
        return None, None, None

    # buscar una ABIERTA en los últimos N meses (por si cambió asignado o mes)
    def find_open_entry_anywhere(_issue_id: str, months_back: int = 24):
        y, m = now.year, now.month
        for _ in range(months_back):
            dtm = datetime(y, m, 1, tzinfo=now.tzinfo)
            k, item, e = find_open_entry_in_month(dtm, _issue_id)
            if e:
                return dtm, k, item, e
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return None, None, None, None

    # chequear si ya existe una cerrada exacta en ese mes para ese issue_id
    def exists_closed_entry(month_dt: datetime, _issue_id: str, entered_iso: str, exited_iso: str) -> bool:
        mk = month_key(month_dt)
        if mk not in logs_cache:
            path = month_filename(month_dt)
            if not os.path.exists(path):
                return False
            logs_cache[mk] = load_month_log(month_dt)
        log = get_log_for(month_dt)
        for it in log.values():
            if it.get("issue_id") != _issue_id:
                continue
            for e in it.get("entries", []):
                if e.get("entered_at") == entered_iso and e.get("exited_at") == exited_iso:
                    return True
        return False
    
    def close_stray_open_entries():
        """
        Cierra entradas ABIERTAS de issues que YA NO están en DOING.
        Revisa solo mes actual y mes previo (no backfill infinito).
        No genera novedades (es cierre de algo existente).
        """
        months_to_check = []
        # mes actual
        months_to_check.append(datetime(now.year, now.month, 1, tzinfo=now.tzinfo))
        # mes previo
        prev_y = now.year if now.month > 1 else now.year - 1
        prev_m = now.month - 1 if now.month > 1 else 12
        months_to_check.append(datetime(prev_y, prev_m, 1, tzinfo=now.tzinfo))

        for mdt in months_to_check:
            mk = month_key(mdt)
            # cargar solo si ya existe archivo (no crear logs vacíos)
            path = month_filename(mdt)
            if not os.path.exists(path):
                continue
            if mk not in logs_cache:
                logs_cache[mk] = load_month_log(mdt)

            log = get_log_for(mdt)
            for item in list(log.values()):
                issue_id = item.get("issue_id")
                # si sigue en DOING, no se cierra
                if issue_id in doing_ids:
                    continue
                # cerrar cualquier abierta
                for e in item.get("entries", []):
                    if e.get("exited_at") is None and e.get("entered_at"):
                        # buscar hora real de salida
                        exited_ts_real = None
                        try:
                            # usamos el issue_key del item si está, si no, lo pedimos al comienzo
                            ikey = item.get("issue_key")
                            if ikey:
                                et_entered, et_exited = get_transition_times(ikey, issue_id)
                                exited_ts_real = et_exited
                        except Exception:
                            exited_ts_real = None
                        if not exited_ts_real:
                            exited_ts_real = now  # fallback: ahora

                        # sanity: no cerrar con end <= start
                        start_dt = parse_jira_datetime(e.get("entered_at"))
                        if not start_dt or exited_ts_real <= start_dt:
                            continue

                        # si ya existe cerrada exacta, salteamos
                        entered_iso = e["entered_at"]
                        exited_iso  = exited_ts_real.isoformat()
                        if exists_closed_entry(mdt, issue_id, entered_iso, exited_iso):
                            continue

                        # cerrar in-place
                        e["exited_at"] = exited_iso
                        e["worked_hours"] = calculate_working_hours(start_dt, exited_ts_real)
                # ordenar por si ajustamos algo
                item["entries"].sort(key=lambda x: (x.get("entered_at") or ""))

    def add_novedad(issue_key: str, assignee_id: str, summary: str, link: str,
                    _issue_id: str, entered_iso: str, exited_iso: str | None):
        k = (_issue_id, entered_iso, exited_iso or "OPEN")
        if k in novedades_set:
            return
        novedades_set.add(k)
        novedades.append({
            "issue_key": issue_key,
            "assignee_id": assignee_id,
            "summary": summary,
            "link": link
        })

    # cerrar una abierta (global) o preparar inserción de una cerrada, sin duplicar
    def upsert_closed_global(month_dt: datetime, _issue_id: str,
                             entered_iso: str, exited_iso: str, worked: float) -> str:
        sdt = parse_jira_datetime(entered_iso)
        edt = parse_jira_datetime(exited_iso)
        if not sdt or not edt or edt <= sdt:
            return "noop"

        # 1) cerrar abierta existente (en cualquier mes, sin crear archivos nuevos)
        om_dt, ok, oitem, oentry = find_open_entry_anywhere(_issue_id)
        if oentry is not None:
            oentry["exited_at"] = exited_iso
            oentry["worked_hours"] = calculate_working_hours(parse_jira_datetime(oentry["entered_at"]), edt)
            oitem["entries"].sort(key=lambda e: (e.get("entered_at") or ""))
            return "updated"

        # 2) si no hay abierta, evitar duplicado exacto (solo si el mes ya existe)
        if exists_closed_entry(month_dt, _issue_id, entered_iso, exited_iso):
            return "noop"

        # 3) no hay abierta ni cerrada exacta: insertar (el caller hará ensure_item y escribirá)
        return "insert"

    # ------------- traer issues -------------
    issues = get_current_issues()
    exited = get_recently_exited_issues()

    # dedup por id
    by_id = {}
    for it in issues + exited:
        by_id[it["id"]] = it
    issues = list(by_id.values())

    doing_ids = {it["id"] for it in get_current_issues()}

    # ------------- procesamiento ------------
    for issue in issues:
        issue_key = issue.get("key")
        fields = issue.get("fields", {})
        issue_id = issue.get("id")

        assignee = fields.get("assignee")
        if assignee:
            assignee_id = assignee.get("name") or "Unassigned"  # Jira Server
            assignee_name = assignee.get("displayName") or "Unassigned"
        else:
            assignee_id = "Unassigned"
            assignee_name = "Unassigned"

        summary = fields.get("summary", "")
        link = build_issue_link(issue_key)
        key = f"{issue_id}-{assignee_id}"

        entered_ts, exited_ts = get_transition_times(issue_key)

        # contenedor por mes (refresca metadatos)
        def ensure_item(dt_for_month: datetime) -> dict:
            log = get_log_for(dt_for_month)
            item = log.get(key)
            if not item:
                item = {
                    "issue_key": issue_key,
                    "issue_id": issue_id,
                    "assignee_id": assignee_id,
                    "assignee_name": assignee_name,
                    "summary": summary,
                    "entries": []
                }
                log[key] = item
            else:
                item["assignee_name"] = assignee_name
                item["summary"] = summary
            return item

        def iso_or_none(dt):
            return dt.isoformat() if dt else None

        def find_entry(entries, e_entered_iso, e_exited_iso):
            for e in entries:
                if e.get("entered_at") == e_entered_iso and e.get("exited_at") == e_exited_iso:
                    return e
            return None

        # ========= Caso A: sigue ABIERTO =========
        if entered_ts and (not exited_ts or exited_ts < entered_ts):
            cur_start = max(entered_ts, month_start_now)
            if cur_start > now:
                continue  # nada que registrar

            # (1) cortes de meses anteriores — SOLO si realmente hay meses anteriores
            while (month_key(cur_start) != month_key(now)):
                y, m = cur_start.year, cur_start.month
                segment_end = last_business_moment_of_year_month(y, m, cur_start.tzinfo)
                if segment_end <= cur_start:
                    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                    cur_start = first_business_moment_of_year_month(ny, nm, cur_start.tzinfo)
                    continue

                worked = calculate_working_hours(cur_start, segment_end)
                e_entered_iso = iso_or_none(cur_start)
                e_exited_iso  = iso_or_none(segment_end)

                res = upsert_closed_global(cur_start, issue_id, e_entered_iso, e_exited_iso, worked)
                if res == "insert":
                    item = ensure_item(cur_start)
                    item["entries"].append({"entered_at": e_entered_iso, "exited_at": e_exited_iso, "worked_hours": worked})
                    item["entries"].sort(key=lambda e: (e.get("entered_at") or ""))
                    add_novedad(issue_key, assignee_id, summary, link, issue_id, e_entered_iso, e_exited_iso)

                ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                cur_start = first_business_moment_of_year_month(ny, nm, cur_start.tzinfo)

            # (2) mes actual: una sola abierta por issue_id
            e_entered_iso = iso_or_none(cur_start)
            worked = calculate_working_hours(cur_start, now)

            k_open, item_open, entry_open = find_open_entry_in_month(now, issue_id)
            if entry_open:
                if entry_open.get("worked_hours") != worked:
                    entry_open["worked_hours"] = worked  # update horas, NO novedad
                item_open["entries"].sort(key=lambda e: (e.get("entered_at") or ""))
            else:
                # crear solo si no existe exactamente esta abierta en este item
                item = ensure_item(now)
                entries = item["entries"]
                if not find_entry(entries, e_entered_iso, None):
                    entries.append({"entered_at": e_entered_iso, "exited_at": None, "worked_hours": worked})
                    add_novedad(issue_key, assignee_id, summary, link, issue_id, e_entered_iso, None)
                    entries.sort(key=lambda e: (e.get("entered_at") or ""))

        # ========= Caso B: ya SALIÓ =========
        elif entered_ts and exited_ts and exited_ts >= entered_ts:
            # si cerró todo antes del mes actual, NO backfill
            if exited_ts <= month_start_now:
                continue

            seg_start = max(entered_ts, month_start_now)
            if seg_start >= exited_ts:
                continue  # nada que registrar

            # meses intermedios (sólo mientras seguís antes de la salida real)
            while (seg_start < exited_ts) and (month_key(seg_start) != month_key(exited_ts)):
                y, m = seg_start.year, seg_start.month
                seg_end = last_business_moment_of_year_month(y, m, seg_start.tzinfo)
                if seg_end <= seg_start:
                    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                    seg_start = first_business_moment_of_year_month(ny, nm, seg_start.tzinfo)
                    continue

                worked = calculate_working_hours(seg_start, seg_end)
                e_entered_iso = iso_or_none(seg_start)
                e_exited_iso  = iso_or_none(seg_end)

                res = upsert_closed_global(seg_start, issue_id, e_entered_iso, e_exited_iso, worked)
                if res == "insert":
                    item = ensure_item(seg_start)
                    item["entries"].append({"entered_at": e_entered_iso, "exited_at": e_exited_iso, "worked_hours": worked})
                    item["entries"].sort(key=lambda e: (e.get("entered_at") or ""))
                    add_novedad(issue_key, assignee_id, summary, link, issue_id, e_entered_iso, e_exited_iso)

                ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
                seg_start = first_business_moment_of_year_month(ny, nm, seg_start.tzinfo)

            # tramo final (en el mes real de salida)
            if exited_ts > seg_start:
                worked = calculate_working_hours(seg_start, exited_ts)
                e_entered_iso = iso_or_none(seg_start)
                e_exited_iso  = iso_or_none(exited_ts)

                res = upsert_closed_global(exited_ts, issue_id, e_entered_iso, e_exited_iso, worked)
                if res == "insert":
                    item = ensure_item(exited_ts)
                    item["entries"].append({"entered_at": e_entered_iso, "exited_at": e_exited_iso, "worked_hours": worked})
                    item["entries"].sort(key=lambda e: (e.get("entered_at") or ""))
                    add_novedad(issue_key, assignee_id, summary, link, issue_id, e_entered_iso, e_exited_iso)

        # ========= Caso C: sin info =========
        else:
            pass

    close_stray_open_entries()
    save_all_logs()
    return novedades



def main():
    now = datetime.now().astimezone()  # timezone-aware local
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    try:
        novedades = update_log_entries(now)
        novedades_path = save_novedades(novedades)
        print(f"OK - Logs actualizados en {OUTPUT_DIR} (mes actual y/o meses previos si hubo rollover).")
        print(f"OK - Novedades de esta corrida en:\n  {novedades_path}")
    except requests.exceptions.Timeout:
        print("ERROR: Timeout al consultar JIRA (aumentá REQUEST_TIMEOUT si es recurrente).")
    except requests.exceptions.SSLError as e:
        print(f"ERROR SSL: {e} (usá VERIFY_SSL=True con certificados válidos).")
    except Exception as e:
        print(f"ERROR inesperado: {e}")


if __name__ == "__main__":
    main()
