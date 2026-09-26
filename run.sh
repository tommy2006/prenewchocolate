#!/usr/bin/env bash
# Start Scout on a Mac or Linux: ./run.sh   (the first run sets everything up)
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8001}"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
[ -f .env ] || cp .env.example .env
echo "Scout is starting on http://localhost:$PORT"
exec .venv/bin/python -m uvicorn app.main:app --port "$PORT"
