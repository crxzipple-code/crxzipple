#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${ROOT_DIR}/.crxzipple/dev-stack/redis"
PID_DIR="${STATE_DIR}/pids"

source "${ROOT_DIR}/scripts/dev/infra-env.sh" >/dev/null

stop_pid_file() {
  local name="$1"
  local pid_file="$2"
  if [[ ! -f "${pid_file}" ]]; then
    echo "${name}: not running"
    return 0
  fi

  local pid
  pid="$(cat "${pid_file}")"
  if [[ -z "${pid}" ]]; then
    rm -f "${pid_file}"
    echo "${name}: cleared empty pid file"
    return 0
  fi

  if kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    for _ in {1..20}; do
      if ! kill -0 "${pid}" >/dev/null 2>&1; then
        break
      fi
      sleep 0.2
    done
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
    echo "${name}: stopped"
  else
    echo "${name}: stale pid ${pid}"
  fi

  rm -f "${pid_file}"
}

stop_matching_processes() {
  local name="$1"
  local pattern="$2"
  local pids
  pids="$(pgrep -f "${pattern}" || true)"
  if [[ -z "${pids}" ]]; then
    echo "${name}: no extra matching processes"
    return 0
  fi

  echo "${name}: stopping matching processes"
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    kill "${pid}" >/dev/null 2>&1 || true
  done <<<"${pids}"

  sleep 0.5

  while IFS= read -r pid; do
    [[ -n "${pid}" ]] || continue
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
  done <<<"${pids}"
}

stop_daemon_services() {
  echo "daemon: stopping via daemon stop-all"
  if (cd "${ROOT_DIR}" && APP_LOG_LEVEL=WARNING "${CRXZIPPLE_PYTHON}" -m crxzipple.main daemon stop-all >/dev/null); then
    echo "daemon: stopped"
  else
    echo "daemon: stop-all failed; falling back to process cleanup" >&2
  fi
  rm -f "${PID_DIR}/daemon.pid"
}

stop_pid_file "frontend" "${PID_DIR}/frontend.pid"
stop_daemon_services
stop_pid_file "api" "${PID_DIR}/api.pid"

stop_matching_processes "frontend" "${ROOT_DIR}/frontend/node_modules/.bin/vite"
stop_matching_processes "api" "python -m crxzipple.main serve"
stop_matching_processes "legacy uvicorn api" "uvicorn crxzipple.interfaces.http.app:app"
stop_matching_processes "legacy daemon supervisor" "python -m crxzipple.main daemon supervise-internal"
stop_matching_processes "orchestration-executor" "python -m crxzipple.main orchestration-executor run-executor"
stop_matching_processes "orchestration-scheduler" "python -m crxzipple.main orchestration-scheduler run-scheduler"
stop_matching_processes "orchestration-observation" "python -m crxzipple.main orchestration-observation run-observation"
stop_matching_processes "tool-worker" "python -m crxzipple.main tool-worker run"
stop_matching_processes "tool-scheduler" "python -m crxzipple.main tool-scheduler run-scheduler"
stop_matching_processes "channel-runtime" "python -m crxzipple.main channel-runtime run"
