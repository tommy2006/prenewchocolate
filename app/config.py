"""Runtime configuration, read from .env at the project root."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# SCOUT_DATA lets you point the app at a separate data folder (e.g. a dev fixture).
DATA_DIR = ROOT / os.getenv("SCOUT_DATA", "data")
IMG_DIR = DATA_DIR / "img"
DB_PATH = DATA_DIR / "db.json"
STATIC_DIR = ROOT / "static"
DATA_DIR.mkdir(exist_ok=True)
IMG_DIR.mkdir(exist_ok=True)

# API keys and the choice of AI live in app/settings.py (Settings screen, with .env as fallback).

# Claude server-side refusal fallbacks (beta). Turn off with CLAUDE_FALLBACKS=0 if your account rejects it.
CLAUDE_FALLBACKS = os.getenv("CLAUDE_FALLBACKS", "1").strip() == "1"


# Caps that keep one discovery run to a few minutes and a few dollars.
MAX_SCORE_PER_JOB = int(os.getenv("MAX_SCORE_PER_JOB", "100"))
SCORE_BATCH_SIZE = 8
SCORE_CONCURRENCY = 4
