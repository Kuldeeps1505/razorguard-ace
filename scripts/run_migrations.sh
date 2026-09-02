#!/usr/bin/env bash
# Run Alembic migrations — safe to run on every deploy
set -euo pipefail
echo "Running migrations..."
alembic upgrade head
echo "Migrations complete."
