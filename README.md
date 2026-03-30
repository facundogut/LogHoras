# LogHoras (rama BISA)

Versión simplificada para traspaso operativo: **solo registra issues activas** desde Jira NBCH en un log mensual JSON.

## Qué incluye esta variante

- Tracker de issues en estado `DOING` (`DES - DOING`, `DISEÑO - DOING`).
- Cálculo de horas hábiles transcurridas para cada issue activa.
- Persistencia mensual en `resultado/jira_log_YYYY-MM.json`.
- Script de cadena (`run_chain.ps1` / `run_chain.vbs`) con un único paso.

## Módulos/servicios indispensables

- `jira_tracker_JSON.py`: entrypoint único a ejecutar por la otra área.
- `loghoras/application/tracker_service.py`: orquesta lectura de activas y armado del log.
- `loghoras/infrastructure/nbch_jira_client.py`: consulta Jira NBCH (search/changelog).
- `loghoras/infrastructure/log_repository.py`: guarda el JSON mensual.
- `loghoras/domain/time_tracking.py`: parseo de fechas y cálculo de horas hábiles.
- `loghoras/shared/config.py`: configuración por variables de entorno.

> Los módulos de espejo/sincronización hacia otro Jira (TOPAZ/NBCH destino) quedan fuera del flujo requerido.

## Configuración para la otra área

### 1) Requisitos

- Python 3.11+
- Acceso de red a `https://nbch.atlassian.net`
- Token de Jira con permisos de lectura de issues y changelog

Instalación:

```bash
pip install -r requirements.txt
```

### 2) Variables de entorno

Configurar en `../boveda/config.env` (o variables del sistema):

```env
USUARIO_JIRA_NBCH=usuario@dominio.com
TOKEN_JIRA_NBCH=token_jira
```

Fallback soportado:

- `TOKEN_JIRA_CDS` (si no está `TOKEN_JIRA_NBCH`)

### 3) Ejecución

Manual:

```bash
python jira_tracker_JSON.py
```

Automatizada en Windows:

- `run_chain.ps1` (PowerShell oculto + log en `logs/chain_YYYYMMDD.log`)
- `run_chain.vbs` (equivalente VBScript)

### 4) Salida esperada

Archivo mensual:

- `resultado/jira_log_YYYY-MM.json`

Cada item guarda:

- issue (`issue_key`, `issue_id`)
- asignado (`assignee_id`, `assignee_name`)
- resumen y link
- entrada activa (`entered_at`, `exited_at: null`, `worked_hours`)

## Validación básica

```bash
python -m compileall jira_tracker_JSON.py loghoras
```
