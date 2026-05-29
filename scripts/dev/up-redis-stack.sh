#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${ROOT_DIR}/.crxzipple/dev-stack/redis"
LOG_DIR="${STATE_DIR}/logs"
PID_DIR="${STATE_DIR}/pids"

API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-4173}"

mkdir -p "${LOG_DIR}" "${PID_DIR}"

source "${ROOT_DIR}/scripts/dev/infra-env.sh" >/dev/null

ensure_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

list_listening_pids() {
  local port="$1"
  lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
}

require_port_available() {
  local name="$1"
  local host="$2"
  local port="$3"
  local pidfile="$4"
  local listeners
  listeners="$(list_listening_pids "${port}")"
  if [[ -z "${listeners}" ]]; then
    return 0
  fi

  if is_running "${pidfile}"; then
    echo "${name}: already running (pid $(cat "${pidfile}"))"
    return 1
  fi

  echo "${name}: ${host}:${port} is already in use by pid(s):" >&2
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    ps -p "${pid}" -o pid=,command=
  done <<<"${listeners}"
  echo "Run 'bash scripts/dev/down-redis-stack.sh' or stop the process above, then retry." >&2
  exit 1
}

is_running() {
  local pid_file="$1"
  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${pid_file}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1
}

start_service() {
  local name="$1"
  local workdir="$2"
  local logfile="$3"
  local pidfile="$4"
  shift 4

  if is_running "${pidfile}"; then
    echo "${name}: already running (pid $(cat "${pidfile}"))"
    return 0
  fi

  "${CRXZIPPLE_PYTHON}" - "${workdir}" "${logfile}" "${pidfile}" "$@" <<'PY'
from __future__ import annotations

import subprocess
import sys

workdir = sys.argv[1]
logfile = sys.argv[2]
pidfile = sys.argv[3]
command = sys.argv[4:]

with open(logfile, "ab", buffering=0) as log:
    process = subprocess.Popen(
        command,
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

with open(pidfile, "w", encoding="utf-8") as handle:
    handle.write(str(process.pid))
PY

  local pid
  pid="$(cat "${pidfile}")"
  sleep 0.5
  if ! kill -0 "${pid}" >/dev/null 2>&1; then
    echo "${name}: failed to stay running" >&2
    echo "  log: ${logfile}" >&2
    rm -f "${pidfile}"
    exit 1
  fi

  echo "${name}: started (pid $(cat "${pidfile}"))"
}

start_daemon_supervisor() {
  local logfile="${LOG_DIR}/daemon.log"
  rm -f "${PID_DIR}/daemon.pid"
  (
    cd "${ROOT_DIR}"
    APP_LOG_LEVEL=WARNING "${CRXZIPPLE_PYTHON}" -m crxzipple.main daemon run \
      --service-set workers \
      --service-set channels-stack \
      --service-set browser-stack
  ) >"${logfile}" 2>&1

  local status
  status="$(
    cd "${ROOT_DIR}" \
      && APP_LOG_LEVEL=WARNING "${CRXZIPPLE_PYTHON}" -m crxzipple.main daemon status 2>&1 \
      || true
  )"
  if ! grep -q '"status": "running"' <<<"${status}"; then
    echo "daemon: failed to start supervisor" >&2
    echo "  log: ${logfile}" >&2
    echo "${status}" >&2
    exit 1
  fi

  echo "daemon: started via daemon run"
}

check_redis() {
  if command -v redis-cli >/dev/null 2>&1; then
    if ! redis-cli -u "${APP_EVENTS_REDIS_URL}" ping >/dev/null 2>&1; then
      echo "Redis is not reachable at ${APP_EVENTS_REDIS_URL}." >&2
      echo "Start Redis first, for example: bash scripts/dev/up-infra.sh" >&2
      exit 1
    fi
    return 0
  fi

  "${CRXZIPPLE_PYTHON}" - <<'PY'
from __future__ import annotations

import os
import sys

from redis import Redis
from redis.exceptions import RedisError

url = os.environ["APP_EVENTS_REDIS_URL"]
try:
    client = Redis.from_url(url, decode_responses=True)
    client.ping()
except RedisError as exc:  # pragma: no cover - shell entrypoint
    print(f"Redis is not reachable at {url}: {exc}", file=sys.stderr)
    print("Start Redis first, for example: bash scripts/dev/up-infra.sh", file=sys.stderr)
    raise SystemExit(1) from exc
PY
}

check_database() {
  "${CRXZIPPLE_PYTHON}" - <<'PY'
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

url = os.environ["APP_DATABASE_URL"]
try:
    engine = create_engine(url)
    with engine.connect() as connection:
        connection.execute(text("select 1"))
except SQLAlchemyError as exc:  # pragma: no cover - shell entrypoint
    print(f"Database is not reachable at {url}: {exc}", file=sys.stderr)
    print("Start Postgres first, for example: bash scripts/dev/up-infra.sh", file=sys.stderr)
    raise SystemExit(1) from exc
PY
}

check_database_url_policy() {
  "${CRXZIPPLE_PYTHON}" - <<'PY'
from __future__ import annotations

import os
import sys

url = os.environ.get("APP_DATABASE_URL", "")
allow_sqlite = os.environ.get("APP_ALLOW_SQLITE_DEV", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
if url.startswith("sqlite") and not allow_sqlite:
    print(
        "Refusing to start the dev stack with SQLite APP_DATABASE_URL.",
        file=sys.stderr,
    )
    print(
        "Use `bash scripts/dev/up-infra.sh` and `source scripts/dev/infra-env.sh`, "
        "or set APP_ALLOW_SQLITE_DEV=1 for an explicit one-off SQLite run.",
        file=sys.stderr,
    )
    raise SystemExit(1)
if not url:
    print("APP_DATABASE_URL is not set; source scripts/dev/infra-env.sh first.", file=sys.stderr)
    raise SystemExit(1)
PY
}

ensure_command npm
ensure_command lsof

if [[ ! -x "${CRXZIPPLE_PYTHON}" ]]; then
  echo "Configured CRXZIPPLE_PYTHON is not executable: ${CRXZIPPLE_PYTHON}" >&2
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "frontend/node_modules is missing. Run 'cd frontend && npm install' first." >&2
  exit 1
fi

check_redis
check_database_url_policy
check_database

(
  cd "${ROOT_DIR}"
  "${CRXZIPPLE_PYTHON}" -m crxzipple.main db upgrade head
  "${CRXZIPPLE_PYTHON}" -m crxzipple.main llm sync-profiles >/dev/null
)

require_port_available "api" "${API_HOST}" "${API_PORT}" "${PID_DIR}/api.pid" || true
require_port_available "frontend" "${FRONTEND_HOST}" "${FRONTEND_PORT}" "${PID_DIR}/frontend.pid" || true

start_service \
  "api" \
  "${ROOT_DIR}" \
  "${LOG_DIR}/api.log" \
  "${PID_DIR}/api.pid" \
  "${CRXZIPPLE_PYTHON}" -m crxzipple.main serve --host "${API_HOST}" --port "${API_PORT}"

start_daemon_supervisor

start_service \
  "frontend" \
  "${ROOT_DIR}/frontend" \
  "${LOG_DIR}/frontend.log" \
  "${PID_DIR}/frontend.pid" \
  npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}" --strictPort

cat <<EOF

Local dev stack is up.
  API:      http://${API_HOST}:${API_PORT}
  Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}

Logs:
  ${LOG_DIR}/api.log
  ${LOG_DIR}/daemon.log
  ${LOG_DIR}/frontend.log

Daemon supervisor logs:
  python -m crxzipple.main daemon logs

Use:
  bash scripts/dev/status-redis-stack.sh
  bash scripts/dev/down-redis-stack.sh
EOF
