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

source "${ROOT_DIR}/scripts/dev/infra-env.sh" >/dev/null

list_listening_pids() {
  local port="$1"
  lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true
}

print_status() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"

  if [[ ! -f "${pid_file}" ]]; then
    echo "${name}: stopped"
    return 0
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    echo "${name}: running (pid ${pid})"
    echo "  log: ${log_file}"
  else
    echo "${name}: stale pid ${pid}"
    echo "  log: ${log_file}"
  fi
}

print_listener_status() {
  local name="$1"
  local host="$2"
  local port="$3"
  local listeners
  listeners="$(list_listening_pids "${port}")"
  if [[ -z "${listeners}" ]]; then
    echo "  listener: none on ${host}:${port}"
    return 0
  fi

  echo "  listener: ${host}:${port}"
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    ps -p "${pid}" -o pid=,command=
  done <<<"${listeners}"
}

print_daemon_status() {
  local output
  if ! output="$(cd "${ROOT_DIR}" && APP_LOG_LEVEL=WARNING "${CRXZIPPLE_PYTHON}" -m crxzipple.main daemon status 2>&1)"; then
    echo "daemon: status unavailable"
    echo "${output}" | sed 's/^/  /'
    return 0
  fi

DAEMON_STATUS_PAYLOAD="${output}" "${CRXZIPPLE_PYTHON}" - <<'PY'
from __future__ import annotations

import json
import os

raw = os.environ["DAEMON_STATUS_PAYLOAD"]
json_start = raw.find("{")
payload = json.loads(raw[json_start:] if json_start >= 0 else raw)
status = payload.get("status", "unknown")
supervisor = payload.get("supervisor") or {}
if supervisor:
    pid = supervisor.get("pid")
    process_id = supervisor.get("id")
    print(f"daemon: {status} (pid {pid}, process {process_id})")
else:
    print(f"daemon: {status}")
print("  logs: python -m crxzipple.main daemon logs")
PY
}

print_status "api" "${PID_DIR}/api.pid" "${LOG_DIR}/api.log"
print_listener_status "api" "${API_HOST}" "${API_PORT}"
print_daemon_status
print_status "frontend" "${PID_DIR}/frontend.pid" "${LOG_DIR}/frontend.log"
print_listener_status "frontend" "${FRONTEND_HOST}" "${FRONTEND_PORT}"

echo
echo "URLs:"
echo "  API:      http://${API_HOST}:${API_PORT}"
echo "  Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
