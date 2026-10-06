#!/bin/sh
# Start the application: migrate the database, add demo data on first start, serve.
set -e

alembic upgrade head

if [ "${INVENTURA_DEMO:-1}" = "1" ]; then
    inventura demo
fi

exec inventura serve --host 0.0.0.0 --port 8000
