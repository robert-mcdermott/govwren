#!/bin/sh
# Start GovWren in a container. Safe to run every time: `init` creates what is missing,
# brings the database up to date, and creates the first administrator only if there is none.
set -eu

if [ -n "${GOVWREN_ADMIN_EMAIL:-}" ] && [ -n "${GOVWREN_ADMIN_PASSWORD:-}" ]; then
    printf '%s' "$GOVWREN_ADMIN_PASSWORD" | govwren init \
        --admin-email "$GOVWREN_ADMIN_EMAIL" \
        --admin-name "${GOVWREN_ADMIN_NAME:-Administrator}" \
        --password-stdin
else
    govwren init </dev/null
fi
unset GOVWREN_ADMIN_PASSWORD
exec govwren serve
