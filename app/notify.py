"""A message to the team's chat when a repeating search finds new creators (a Slack, Teams or Discord webhook).

Optional: the webhook address goes in Settings (or NOTIFY_WEBHOOK_URL in .env). Only https addresses on the public
internet are called, and a failing webhook never fails a search.
"""
import logging
import urllib.parse

import httpx

from . import settings
from .contacts import _public
from .markets import MARKETS

log = logging.getLogger("scout")


async def send(text: str, url: str | None = None) -> str:
    """Post `text`; returns "" on success, else what went wrong."""
    url = (url or settings.data_key("notify_webhook")).strip()
    if not url:
        return "No webhook address saved"
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or not await _public(parts.hostname):
        return "The webhook address must be a public https:// address"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.post(url, json={"text": text, "content": text})  # Slack/Teams read "text", Discord "content"
    except httpx.HTTPError as e:
        return f"Couldn't reach the webhook ({type(e).__name__})"
    return "" if r.status_code < 300 else f"The webhook answered {r.status_code}"


def summary(label: str, new: list[tuple[dict, dict]], rising: list[tuple[dict, dict]], link: str = "") -> str:
    def who(c, m):
        where = MARKETS.get(m.get("country") or c.get("country") or "", {}).get("name", "")
        return f"{c.get('name')} (Fit {m.get('fit')}, {c.get('followers') or 0:,} followers{', ' + where if where else ''})"
    lines = [f"Scout found {len(new)} new creator{'s' if len(new) != 1 else ''}: {label}"]
    if new:
        lines.append("Best: " + "; ".join(who(c, m) for c, m in new[:3]))
    if rising:
        lines.append("Rising: " + "; ".join(f"{c.get('name')} (views +{round(100 * c['views_trend'])}% in 30 days)" for c, _ in rising[:3]))
    if link:
        lines.append(link)
    return "\n".join(lines)
