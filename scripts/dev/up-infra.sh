#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker" >&2
  echo "Install Docker Desktop or another Docker runtime, then retry." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required: docker compose" >&2
  exit 1
fi

(
  cd "${ROOT_DIR}"
  docker compose up -d postgres redis
)

source "${ROOT_DIR}/scripts/dev/infra-env.sh" >/dev/null

cat <<EOF
Dev infra is up.
  Postgres: postgresql+psycopg://${CRXZIPPLE_POSTGRES_USER}:<redacted>@${CRXZIPPLE_POSTGRES_HOST}:${CRXZIPPLE_POSTGRES_PORT}/${CRXZIPPLE_POSTGRES_DB}
  Redis:    ${APP_EVENTS_REDIS_URL}

Next:
  source scripts/dev/infra-env.sh
  python -m crxzipple.main db upgrade head
EOF
