@echo off
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
if not exist .env copy .env.example .env >nul
echo Scout is starting on http://localhost:8001
.venv\Scripts\python -m uvicorn app.main:app --port 8001
