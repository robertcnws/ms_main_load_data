#!/usr/bin/env bash
set -Eeuo pipefail

# ================== Config por variables de entorno (con defaults) ==================
: "${DJANGO_SETTINGS_MODULE:=ms_main_load_data.settings}"
: "${PORT:=8000}"

# Celery Concurrency por cola
: "${ZOHO_CATALOG_CONCURRENCY:=2}"
: "${ZOHO_SALES_CONCURRENCY:=1}"       # bajar a 1 para evitar hog/solapes
: "${ZOHO_SHIPMENTS_CONCURRENCY:=1}"   # 1 para anti-429
: "${SENITRON_CONCURRENCY:=2}"
: "${CELERY_LOGLEVEL:=info}"
: "${CELERY_EVENTS:=1}" # 1=habilita -E, 0=no

# Límites por cola (soft/hard timelimits)  -> ajusta si lo necesitas
: "${ZOHO_SALES_SOFT_TL:=1080}"        # 18 min
: "${ZOHO_SALES_HARD_TL:=1200}"        # 20 min
: "${ZOHO_SHIP_SOFT_TL:=540}"          # 9 min
: "${ZOHO_SHIP_HARD_TL:=600}"          # 10 min
: "${ZOHO_CATALOG_SOFT_TL:=420}"       # 7 min
: "${ZOHO_CATALOG_HARD_TL:=480}"       # 8 min
: "${SENITRON_SOFT_TL:=600}"
: "${SENITRON_HARD_TL:=720}"

# Prefetch / estabilidad (comunes)
: "${CELERY_PREFETCH:=1}"              # 1 = no acaparar tareas
: "${CELERY_MAX_TASKS_PER_CHILD:=20}"  # reciclar workers
: "${CELERY_OPTIMIZATION:=fair}"       # -O fair

# Flower
: "${FLOWER_ENABLE:=1}"       # 1=on, 0=off
: "${FLOWER_PORT:=5555}"
: "${FLOWER_URL_PREFIX:=/flower}"
: "${FLOWER_USER:=admin}"
: "${FLOWER_PASSWORD:=admin}"

# Inspector loop (logs periódicos de queues/registered)
: "${INSPECTOR_INTERVAL:=60}"        # 0 para desactivar
: "${INSPECTOR_WAIT_TIMEOUT:=60}"    # seg máx para esperar nodos al inicio

# Gunicorn
: "${GUNICORN_WORKERS:=3}"

# Purga/Limpieza inicial (mejor OFF en prod)
: "${PURGE_ON_BOOT:=0}"                               # <--- CAMBIO: evita perder colas en reinicios
: "${QUEUES_TO_PURGE:=celery,default,zoho_catalog,zoho_sales,zoho_shipments,senitron}"
: "${PURGE_TIMEOUT:=6}"

# Beat schedule (archivo local)
: "${SCHEDULE_RESET_ON_BOOT:=0}"
: "${CELERYBEAT_SCHEDULE_PATH:=celerybeat-schedule}"

# ================== Helpers ==================
pids=()

log_env_absence () {
  if [ ! -f "/.env" ]; then
    echo "No .env at /.env (ok if you inject env via Docker)"
  fi
}

purge_queues() {
  IFS=',' read -ra QLIST <<< "$QUEUES_TO_PURGE"
  echo "[entrypoint] Purging Celery queues: ${QLIST[*]}"
  for q in "${QLIST[@]}"; do
    celery -A ms_main_load_data purge -Q "$q" -f || true
  done
}

reset_beat_schedule () {
  if [ -f "${CELERYBEAT_SCHEDULE_PATH}" ]; then
    echo "[entrypoint] Deleting beat schedule file: ${CELERYBEAT_SCHEDULE_PATH}"
    rm -f "${CELERYBEAT_SCHEDULE_PATH}" || true
  fi
}

start_bg () {
  # $1 = comando (string)
  bash -lc "$1" &
  pids+=($!)
}

cleanup () {
  echo "[entrypoint] Stopping background processes..."
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
    fi
  done
  wait || true
}
trap cleanup EXIT INT TERM

wait_for_nodes () {
  local deadline=$(( $(date +%s) + INSPECTOR_WAIT_TIMEOUT ))
  echo "[entrypoint] Waiting up to ${INSPECTOR_WAIT_TIMEOUT}s for Celery nodes (zoho@*, senitron@*)..."
  while [ "$(date +%s)" -lt "$deadline" ]; do
    if celery -A ms_main_load_data status 2>/dev/null | grep -E 'zoho@|senitron@' >/dev/null; then
      echo "[entrypoint] Celery nodes detected."
      return 0
    fi
    sleep 3
  done
  echo "[entrypoint] WARNING: No Celery nodes detected in time (continuing anyway)."
  return 1
}

flower_available () {
  celery --help 2>/dev/null | grep -q 'flower' || return 1
  return 0
}

# ================== Limpiezas antes de arrancar ==================
log_env_absence

if [ "$PURGE_ON_BOOT" = "1" ]; then
  echo "[entrypoint] Purging queues before starting workers..."
  purge_queues
  sleep "$PURGE_TIMEOUT"
fi

if [ "$SCHEDULE_RESET_ON_BOOT" = "1" ]; then
  reset_beat_schedule
fi

# ================== Django setup ==================
echo "[entrypoint] Running Django setup..."
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --no-input
python init_scripts.py

# ================== Celery workers & beat ==================
echo "[entrypoint] Starting Celery workers and beat..."

events_flag=""
if [ "${CELERY_EVENTS}" = "1" ]; then
  events_flag="-E"
fi

# Flags comunes (pool prefork, fair scheduler, prefetch=1 y reciclado de procesos)
COMMON_FLAGS="-O ${CELERY_OPTIMIZATION} --pool=prefork --prefetch-multiplier=${CELERY_PREFETCH} --max-tasks-per-child=${CELERY_MAX_TASKS_PER_CHILD}"

# Cada worker con su time limit y concurrency específicos
start_bg "celery -A ms_main_load_data worker -Q zoho_catalog   -c ${ZOHO_CATALOG_CONCURRENCY}   -n zoho_catalog@%h   --loglevel=${CELERY_LOGLEVEL} ${events_flag} ${COMMON_FLAGS} --soft-time-limit=${ZOHO_CATALOG_SOFT_TL} --time-limit=${ZOHO_CATALOG_HARD_TL}"
start_bg "celery -A ms_main_load_data worker -Q zoho_sales     -c ${ZOHO_SALES_CONCURRENCY}     -n zoho_sales@%h     --loglevel=${CELERY_LOGLEVEL} ${events_flag} ${COMMON_FLAGS} --soft-time-limit=${ZOHO_SALES_SOFT_TL}   --time-limit=${ZOHO_SALES_HARD_TL}"
start_bg "celery -A ms_main_load_data worker -Q zoho_shipments -c ${ZOHO_SHIPMENTS_CONCURRENCY} -n zoho_shipments@%h --loglevel=${CELERY_LOGLEVEL} ${events_flag} ${COMMON_FLAGS} --soft-time-limit=${ZOHO_SHIP_SOFT_TL}     --time-limit=${ZOHO_SHIP_HARD_TL}"
start_bg "celery -A ms_main_load_data worker -Q senitron       -c ${SENITRON_CONCURRENCY}       -n senitron@%h       --loglevel=${CELERY_LOGLEVEL} ${events_flag} ${COMMON_FLAGS} --soft-time-limit=${SENITRON_SOFT_TL}       --time-limit=${SENITRON_HARD_TL}"

start_bg "celery -A ms_main_load_data beat --loglevel=${CELERY_LOGLEVEL}"

# ================== Flower (UI) ==================
if [ "${FLOWER_ENABLE}" = "1" ]; then
  if flower_available; then
    echo "[entrypoint] Starting Flower on :${FLOWER_PORT}${FLOWER_URL_PREFIX}"
    start_bg "celery -A ms_main_load_data flower \
      --port=${FLOWER_PORT} \
      --url_prefix='${FLOWER_URL_PREFIX}' \
      --basic_auth='${FLOWER_USER}:${FLOWER_PASSWORD}'"
  else
    echo "[entrypoint] WARNING: Flower no está instalado (o no registra el subcomando). Saltando inicio de Flower."
  fi
fi

# ================== Inspector loop ==================
if [ "${INSPECTOR_INTERVAL}" != "0" ]; then
  wait_for_nodes || true
  start_bg "while true; do \
    echo '[inspector] ====='; date; \
    echo '[inspector] celery status:'; \
    celery -A ms_main_load_data status || true; \
    echo '[inspector] active_queues (filtered if nodes exist, otherwise without filter):'; \
    if celery -A ms_main_load_data status 2>/dev/null | grep -E 'zoho_shipments@|zoho_catalog@|zoho_sales@|senitron@' >/dev/null; then \
      celery -A ms_main_load_data inspect active_queues -d 'zoho_shipments@*' -d 'zoho_catalog@*' -d 'zoho_sales@*' -d 'senitron@*' || true; \
    else \
      celery -A ms_main_load_data inspect active_queues || true; \
    fi; \
    echo '[inspector] registered tasks (primeras 120 líneas):'; \
    if celery -A ms_main_load_data status 2>/dev/null | grep -E 'zoho_shipments@|zoho_catalog@|zoho_sales@|senitron@' >/dev/null; then \
      celery -A ms_main_load_data inspect registered -d 'zoho_shipments@*' -d 'zoho_catalog@*' -d 'zoho_sales@*' -d 'senitron@*' | head -n 120 || true; \
    else \
      celery -A ms_main_load_data inspect registered | head -n 120 || true; \
    fi; \
    sleep ${INSPECTOR_INTERVAL}; \
  done"
fi

# ================== Gunicorn (foreground) ==================
echo "[entrypoint] Starting Gunicorn on :${PORT}"
exec gunicorn ms_main_load_data.asgi:application \
  -w "${GUNICORN_WORKERS}" \
  -k uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT}"
