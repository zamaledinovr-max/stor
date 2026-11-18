#!/usr/bin/env bash
# Starts migrations, the FastAPI/Mini App server and the aiogram bot.
#
# Environment switches:
#   RUN_API=0  - do not start uvicorn (bot-only container)
#   RUN_BOT=0  - do not start the bot (API-only container)
#   APP_PORT   - HTTP port, must match run.containerPort in amvera.yml (default 8000)
#   LOCAL_STORAGE_DIR - photo directory (Amvera persistent volume: /data/media)

set -Eeuo pipefail

APP_PORT="${APP_PORT:-8000}"
LOCAL_STORAGE_DIR="${LOCAL_STORAGE_DIR:-/data/media}"
export LOCAL_STORAGE_DIR

echo "[start] storage directory: $LOCAL_STORAGE_DIR"

# The container starts as root so it can fix ownership of the mounted
# persistent volume, then it re-executes itself as the unprivileged user.
if [ "$(id -u)" = "0" ] && command -v gosu >/dev/null 2>&1 && id appuser >/dev/null 2>&1; then
    mkdir -p "$LOCAL_STORAGE_DIR"
    chown -R appuser:appuser /data 2>/dev/null || true
    echo "[start] dropping privileges to appuser"
    exec gosu appuser bash "$0" "$@"
fi

mkdir -p "$LOCAL_STORAGE_DIR"

echo "[start] applying database migrations"
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    alembic upgrade head
else
    echo "[start] migrations skipped (RUN_MIGRATIONS=0)"
fi

pids=()

cleanup() {
    echo "[start] stopping child processes..."
    for pid in "${pids[@]:-}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    wait || true
}
trap 'cleanup; exit 143' INT TERM

if [ "${RUN_API:-1}" = "1" ]; then
    echo "[start] uvicorn on 0.0.0.0:$APP_PORT"
    uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "$APP_PORT" \
        --proxy-headers \
        --forwarded-allow-ips='*' &
    pids+=("$!")
fi

if [ "${RUN_BOT:-1}" = "1" ]; then
    echo "[start] aiogram bot (long polling)"
    python -m app.bot.main &
    pids+=("$!")
fi

if [ "${#pids[@]}" -eq 0 ]; then
    echo "[start] ERROR: both RUN_API and RUN_BOT are disabled" >&2
    exit 1
fi

echo "[start] running: ${pids[*]}"
wait -n "${pids[@]}"
status=$?
echo "[start] a child process exited with status $status" >&2
cleanup

# Exit non-zero so the platform restarts the container if one process dies.
if [ "$status" -eq 0 ]; then
    status=1
fi
exit "$status"
