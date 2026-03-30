# LogHoras

Automatizaciones para seguir horas de trabajo en Jira NBCH, exportarlas y generar novedades/tareas espejo en Jira TOPAZ (proyecto `NBCH` en Topsystems).

## Objetivo del repo

Este repositorio reúne scripts de soporte para tres flujos principales:

1. **Tracking de horas desde Jira NBCH**: detecta entradas y salidas de estados `DOING`, calcula horas hábiles y persiste logs mensuales en JSON.
2. **Sincronización de novedades hacia Jira TOPAZ**: toma `resultado/novedades.json`, evita duplicados por clave CDS y crea issues espejo en el proyecto `NBCH` de TOPAZ/Topsystems.
3. **Exportación y salidas auxiliares**: convierte logs a CSV y guarda resultados listos para consumo manual o por otros procesos.

## Estructura actual

### Entry points

- `jira_tracker_JSON.py`: entrypoint del tracker de horas. Construye dependencias y ejecuta el caso de uso principal.
- `enviar_novedades.py`: entrypoint de sincronización de novedades hacia Jira TOPAZ.
- `json_to_csv.py`: utilidad puntual para convertir logs JSON a CSV.
- `run_chain.ps1` / `run_chain.vbs`: scripts de orquestación para ejecutar la cadena completa.
- Ambos scripts escriben en `logs/chain_YYYYMMDD.log` y ahora capturan también la salida estándar y de error de cada paso para facilitar el diagnóstico.

### Paquete `loghoras/`

La lógica nueva quedó separada en capas para que el mantenimiento sea más simple.

#### `loghoras/shared/`
Configuración y acceso a variables de entorno.

- `config.py`: configuración del tracker de Jira NBCH (`TrackerConfig`).
- `topaz_config.py`: configuración del sincronizador hacia Jira TOPAZ (`TopazSyncConfig`).

#### `loghoras/domain/`
Reglas de negocio puras, sin llamadas HTTP ni acceso a disco.

- `time_tracking.py`: parsing de fechas Jira, días hábiles, cálculo de horas y helpers de meses.
- `novedades.py`: validación del archivo de novedades, extracción de número CDS y armado del summary destino.

#### `loghoras/infrastructure/`
Integraciones externas y persistencia.

- `nbch_jira_client.py`: integración con Jira NBCH para leer issues, changelog y transiciones.
- `log_repository.py`: lectura/escritura de logs mensuales y `novedades.json`.
- `topaz_jira_client.py`: integración con Jira TOPAZ para buscar duplicados, resolver asignados y crear issues en el proyecto `NBCH`.
- `issue_type_client.py`: integración con el servicio SAI que sugiere el tipo de issue.
- `novedades_repository.py`: lectura/escritura del flujo `novedades.json` -> `creados.json`.

#### `loghoras/application/`
Casos de uso que coordinan dominio + infraestructura.

- `tracker_service.py`: sincroniza estados DOING y actualiza logs mensuales.
- `novedades_service.py`: procesa novedades, evita duplicados y crea issues en Jira TOPAZ.

## Carpetas de datos

- `resultado/`: logs mensuales `jira_log_YYYY-MM.json` y `novedades*.json`.
- `exports/`: CSVs derivados de los logs.
- `salidaTeams/`: salidas del proceso de creación de issues en Jira TOPAZ.

## Flujo recomendado de mantenimiento

### Tracker Jira NBCH

1. Ajustar variables de entorno en `../boveda/config.env`.
2. Ejecutar `jira_tracker_JSON.py`.
3. Revisar `resultado/jira_log_YYYY-MM.json` y `resultado/novedades.json`.

Si hay que cambiar reglas de negocio:
- horas hábiles / fechas: `loghoras/domain/time_tracking.py`
- orquestación del flujo: `loghoras/application/tracker_service.py`
- acceso a Jira NBCH: `loghoras/infrastructure/nbch_jira_client.py`
- paths o parámetros globales: `loghoras/shared/config.py`

### Sincronización a Jira TOPAZ

1. Ejecutar `enviar_novedades.py` con el input deseado.
2. Revisar `salidaTeams/creados.json`.

Si hay que modificar comportamiento:
- validación y formato de novedades: `loghoras/domain/novedades.py`
- reglas del flujo: `loghoras/application/novedades_service.py`
- acceso a Jira TOPAZ: `loghoras/infrastructure/topaz_jira_client.py`
- clasificación por IA: `loghoras/infrastructure/issue_type_client.py`
- configuración: `loghoras/shared/topaz_config.py`

## Variables de entorno usadas

### Tracker Jira NBCH

- `USUARIO_JIRA_NBCH` (usar `fgperez@topazevolution.com`)
- `TOKEN_JIRA_NBCH` (token obtenido desde la bóveda)
- `TOKEN_JIRA_CDS` (fallback histórico si no está `TOKEN_JIRA_NBCH`)

### Sync Jira TOPAZ

- `USUARIO_JIRA_NBCH`
- `TOKEN_JIRA_NBCH`
- `JIRA_PROJECT`
- `API_KEY_SAI`

## Validación básica

Comandos útiles:

```bash
python -m compileall jira_tracker_JSON.py enviar_novedades.py loghoras
python json_to_csv.py resultado/jira_log_2026-03.json exports/jira_entries_flat_2026-03.csv
```

## Nota

Los archivos de `resultado/`, `exports/` y `salidaTeams/` son datos generados o insumos operativos. La lógica a mantener vive principalmente en `loghoras/` y en los entrypoints del root.
