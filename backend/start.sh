#!/bin/sh
set -eu

echo "Running database migrations..."
alembic upgrade head

echo "Seeding learning content..."
python -m app.seed_content

echo "Starting Telegram bot polling..."
python -m app.bot &
BOT_PID=$!

cleanup() {
  echo "Stopping Telegram bot..."
  kill "$BOT_PID" 2>/dev/null || true
  wait "$BOT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting Lingvera API..."
uvicorn app.main:app --host 0.0.0.0 --port 8000
