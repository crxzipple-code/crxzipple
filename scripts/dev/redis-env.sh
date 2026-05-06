#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${BASH_VERSION:-}" ]]; then
  SCRIPT_PATH="${BASH_SOURCE[0]}"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  SCRIPT_PATH="${(%):-%x}"
else
  SCRIPT_PATH="$0"
fi

ROOT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")/../.." && pwd)"

resolve_python() {
  if [[ -n "${CRXZIPPLE_PYTHON:-}" ]]; then
    echo "${CRXZIPPLE_PYTHON}"
    return 0
  fi

  local candidates=()

  if [[ "${CONDA_DEFAULT_ENV:-}" == "crxzipple" && -n "${CONDA_PREFIX:-}" ]]; then
    candidates+=("${CONDA_PREFIX}/bin/python")
  fi

  candidates+=(
    "${ROOT_DIR}/.venv/bin/python"
    "${HOME}/anaconda3/envs/crxzipple/bin/python"
    "${HOME}/miniconda3/envs/crxzipple/bin/python"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if python_is_usable "${candidate}"; then
      echo "${candidate}"
      return 0
    fi
  done

  command -v python
}

python_is_usable() {
  local candidate="$1"
  [[ -x "${candidate}" ]] || return 1
  PYTHONPATH="${ROOT_DIR}/src" "${candidate}" - <<'PY' >/dev/null 2>&1
import sys

if sys.version_info < (3, 11):
    raise SystemExit(1)

import crxzipple  # noqa: F401
PY
}

export CRXZIPPLE_PYTHON="$(resolve_python)"
export PYTHONPATH="${PYTHONPATH:-$ROOT_DIR/src}"
export APP_EVENTS_BACKEND="${APP_EVENTS_BACKEND:-redis}"
export CRXZIPPLE_REDIS_PORT="${CRXZIPPLE_REDIS_PORT:-6379}"
export APP_EVENTS_REDIS_URL="${APP_EVENTS_REDIS_URL:-redis://127.0.0.1:${CRXZIPPLE_REDIS_PORT}/0}"
export APP_EVENTS_REDIS_KEY_PREFIX="${APP_EVENTS_REDIS_KEY_PREFIX:-crx:events}"
export APP_EVENTS_REDIS_BLOCK_MS="${APP_EVENTS_REDIS_BLOCK_MS:-1000}"
export APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS="${APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS:-3600}"

cat <<EOF
Redis events env loaded:
  CRXZIPPLE_PYTHON=$CRXZIPPLE_PYTHON
  PYTHONPATH=$PYTHONPATH
  APP_EVENTS_BACKEND=$APP_EVENTS_BACKEND
  APP_EVENTS_REDIS_URL=$APP_EVENTS_REDIS_URL
  APP_EVENTS_REDIS_KEY_PREFIX=$APP_EVENTS_REDIS_KEY_PREFIX
EOF
