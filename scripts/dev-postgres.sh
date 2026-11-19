#!/bin/sh
# Start (or reuse) a disposable PostgreSQL container for running GovWren's tests against
# PostgreSQL. Works with podman or docker. Development use only.
#
#   scripts/dev-postgres.sh          start it and print the test URL
#   scripts/dev-postgres.sh stop     stop and remove it
#
# Then run scripts/test-both.sh, or:
#   GOVWREN_TEST_DATABASE=postgres GOVWREN_TEST_POSTGRES_URL=<printed url> \
#     uv run --extra postgres pytest
set -eu

NAME="${GOVWREN_PG_CONTAINER:-govwren-pg-test}"
PORT="${GOVWREN_PG_PORT:-55436}"
IMAGE="${GOVWREN_PG_IMAGE:-docker.io/library/postgres:16}"
PASSWORD="${GOVWREN_PG_PASSWORD:-govwren-dev}"

if command -v podman >/dev/null 2>&1; then ENGINE=podman
elif command -v docker >/dev/null 2>&1; then ENGINE=docker
else echo "Neither podman nor docker is installed." >&2; exit 1
fi

if [ "${1:-start}" = "stop" ]; then
  "$ENGINE" rm -f "$NAME" >/dev/null 2>&1 || true
  echo "Removed $NAME"
  exit 0
fi

if ! "$ENGINE" container exists "$NAME" 2>/dev/null && \
   ! "$ENGINE" inspect "$NAME" >/dev/null 2>&1; then
  "$ENGINE" run -d --rm --name "$NAME" \
    -e POSTGRES_USER=govwren -e POSTGRES_PASSWORD="$PASSWORD" -e POSTGRES_DB=govwren_test \
    -p "127.0.0.1:$PORT:5432" "$IMAGE" \
    -c max_connections=300 -c fsync=off -c synchronous_commit=off -c full_page_writes=off \
    >/dev/null  # durability off: these databases are thrown away
fi

printf "Waiting for PostgreSQL on 127.0.0.1:%s " "$PORT"
i=0
until "$ENGINE" exec "$NAME" pg_isready -U govwren -d govwren_test >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -gt 60 ] && { echo " timed out" >&2; exit 1; }
  printf "."
  sleep 1
done
echo " ready"
echo "postgresql+psycopg://govwren:$PASSWORD@127.0.0.1:$PORT/govwren_test"
