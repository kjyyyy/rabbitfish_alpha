#!/usr/bin/env bash
# Entrypoint: optionally bring the schema up to date, then run `alphalab <args>`.
#
# ALPHALAB_AUTO_MIGRATE=1  run `alembic upgrade head` before the command.
#   Fine for a single-writer laptop or a one-shot job. Leave it OFF for a
#   multi-replica deployment and run migrations as a separate step, or two
#   replicas will race on the same upgrade.
set -euo pipefail

if [ "${ALPHALAB_AUTO_MIGRATE:-0}" = "1" ]; then
  echo "entrypoint: alembic upgrade head (DATABASE_URL=${DATABASE_URL:-sqlite:///runs/alphalab.db})" >&2
  python -m alembic upgrade head
fi

# `docker run alphalab bash` / `sh` for debugging; anything else is a subcommand.
case "${1:-}" in
  bash|sh|python|pytest|alembic|uvicorn) exec "$@" ;;
esac

exec alphalab "$@"
