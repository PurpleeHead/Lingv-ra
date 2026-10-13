#!/bin/sh
set -eu

echo "Running database migrations..."
alembic upgrade head

echo "Seeding learning content..."
python -m app.seed_content

echo "Starting Telegram bot polling..."
python -m app.bot &

echo "Starting Lingvera API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
