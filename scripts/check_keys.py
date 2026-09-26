"""Check that the configured keys work (the same checks as the Settings screen's Test buttons).

Usage:  .venv/Scripts/python scripts/check_keys.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import llm, settings  # noqa: E402
from app.checks import CheckError, check_apify, check_youtube  # noqa: E402


async def run(name, coro):
    try:
        print(f"{name:9}: OK, {await coro}")
    except (CheckError, llm.LLMError) as e:
        print(f"{name:9}: {e}")


async def main():
    ai = settings.ai_config()
    await run(f"AI", llm.test_ai(ai) if ai["ready"] else _missing(f"{ai['label']} isn't set up (key or model missing)"))
    await run("YouTube", check_youtube(settings.youtube_key()))
    await run("Apify", check_apify(settings.apify_token()))


async def _missing(msg):
    raise CheckError(msg)


if __name__ == "__main__":
    asyncio.run(main())
