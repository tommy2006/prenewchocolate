"""Messages to the team's chat when a repeating search finds new creators: Slack and/or Microsoft Teams.

Each has its own incoming-webhook address in Settings (or SLACK_WEBHOOK_URL / TEAMS_WEBHOOK_URL in .env) and its own
format:
- Slack: {"text": ...} in Slack's markup (*bold*, <url|text> links).
- Teams: a message carrying an Adaptive Card, the format of the Workflows app's "Post to a channel when a webhook
  request is received" (the older Office 365 connector webhooks accept it too).
Only https addresses on the public internet are called, and a failing webhook never fails a search.
"""
import logging
import urllib.parse
from dataclasses import dataclass, field

import httpx

from . import settings
from .contacts import _public
from .markets import MARKETS

log = logging.getLogger("scout")
CHANNELS = {"slack": "slack_webhook", "teams": "teams_webhook"}  # channel -> its setting
NAMES = {"slack": "Slack", "teams": "Microsoft Teams"}


@dataclass
class Message:
    title: str
    lines: list[str] = field(default_factory=list)
    link: str = ""


def _slack_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def slack_payload(msg: Message) -> dict:
    text = f"*{_slack_text(msg.title)}*" + "".join(f"\n• {_slack_text(line)}" for line in msg.lines)
    if msg.link:
        text += f"\n<{msg.link}|Open Scout>"
    return {"text": text}


def teams_payload(msg: Message) -> dict:
    body = [{"type": "TextBlock", "text": msg.title, "weight": "Bolder", "size": "Medium", "wrap": True}]
    body += [{"type": "TextBlock", "text": f"• {line}", "wrap": True, "spacing": "Small"} for line in msg.lines]
    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
            "body": body}
    if msg.link:
        card["actions"] = [{"type": "Action.OpenUrl", "title": "Open Scout", "url": msg.link}]
    return {"type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None, "content": card}]}


PAYLOADS = {"slack": slack_payload, "teams": teams_payload}


async def post(channel: str, msg: Message, url: str | None = None) -> str:
    """Send `msg` to one channel; "" on success, else what went wrong (in words for the Settings screen)."""
    url = (url or settings.data_key(CHANNELS[channel])).strip()
    if not url:
        return f"No {NAMES[channel]} webhook address saved"
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or not await _public(parts.hostname):
        return "The webhook address must be a public https:// address"
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(url, json=PAYLOADS[channel](msg))
    except httpx.HTTPError as e:
        return f"Couldn't reach {NAMES[channel]} ({type(e).__name__})"
    if r.status_code >= 300:  # Slack answers 200 "ok"; Teams workflows 202
        return f"{NAMES[channel]} answered {r.status_code}: {r.text[:120]}"
    return ""


async def post_all(msg: Message) -> dict[str, str]:
    """Send to every channel that has a webhook; {channel: problem} for the ones that failed."""
    problems = {}
    for channel, key in CHANNELS.items():
        if settings.data_key(key):
            problem = await post(channel, msg)
            if problem:
                problems[channel] = problem
    return problems


def any_channel() -> bool:
    return any(settings.data_key(key) for key in CHANNELS.values())


def test_message() -> Message:
    return Message("Scout is connected", ["New creators from repeating searches will be posted here."])


def watch_message(label: str, new: list[tuple[dict, dict]], rising: list[tuple[dict, dict]], link: str = "") -> Message:
    def who(c, m):
        where = MARKETS.get(m.get("country") or c.get("country") or "", {}).get("name", "")
        return f"{c.get('name')}: Fit {m.get('fit')}, {c.get('followers') or 0:,} followers" + (f", {where}" if where else "")
    lines = [f"Best: {who(c, m)}" for c, m in new[:3]]
    lines += [f"Rising: {c.get('name')}, views +{round(100 * c['views_trend'])}% in 30 days" for c, _ in rising[:3]]
    return Message(f"Scout found {len(new)} new creator{'s' if len(new) != 1 else ''}: {label}", lines, link)
