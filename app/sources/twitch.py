"""Twitch discovery via the official Helix API (free: a Client ID and Secret from dev.twitch.tv/console).

Twitch has a language filter, which makes small markets easy to reach: live streams in Finnish, channels
whose broadcast language is Estonian... Searches:
1. Live streams in the market's language, overall and for each creator type that is a game (Minecraft...).
2. Channel search for each creator type, kept only when the channel broadcasts in the market's language.
Twitch has no view counts per stream in the API, so "views per video" are the views of recent past
broadcasts and highlights (lower than live viewers). Followers need one request per channel.
"""
import asyncio
import time

import httpx

from .. import settings
from ..metrics import in_range

API = "https://api.twitch.tv/helix"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
_token: dict = {"value": "", "expires": 0.0, "client": ""}
_calls = asyncio.Semaphore(6)


class TwitchError(Exception):
    pass


async def _auth(http: httpx.AsyncClient, client_id: str, secret: str, force: bool = False) -> str:
    """An app access token (client credentials), cached until shortly before it expires."""
    if not force and _token["value"] and _token["client"] == client_id and _token["expires"] > time.time() + 60:
        return _token["value"]
    r = await http.post(TOKEN_URL, params={"client_id": client_id, "client_secret": secret,
                                           "grant_type": "client_credentials"}, timeout=20)
    if r.status_code != 200:
        try:
            msg = r.json().get("message") or r.text[:200]
        except ValueError:
            msg = r.text[:200]
        raise TwitchError(f"Twitch login: {msg}")
    data = r.json()
    _token.update(value=data["access_token"], expires=time.time() + data.get("expires_in", 3600), client=client_id)
    return _token["value"]


async def _get(http: httpx.AsyncClient, path: str, **params) -> dict:
    client_id, secret = settings.twitch_keys()
    if not client_id or not secret:
        raise TwitchError("No Twitch Client ID and Secret yet")
    for attempt in (0, 1):
        token = await _auth(http, client_id, secret, force=bool(attempt))
        async with _calls:
            r = await http.get(f"{API}/{path}", params=params, timeout=20,
                               headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"})
        if r.status_code == 401 and not attempt:
            continue  # token expired or revoked: log in again once
        if r.status_code != 200:
            try:
                msg = r.json().get("message") or r.text[:200]
            except ValueError:
                msg = r.text[:200]
            raise TwitchError(f"Twitch {path}: {msg}")
        return r.json()
    raise TwitchError("Twitch refused the login")


async def check(client_id: str, secret: str) -> str:
    """Settings "Test": log in and read one category."""
    try:
        async with httpx.AsyncClient() as http:
            token = await _auth(http, client_id, secret, force=True)
            r = await http.get(f"{API}/games/top", params={"first": 1}, timeout=20,
                               headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise TwitchError(f"Couldn't reach Twitch ({type(e).__name__})") from e
    if r.status_code != 200:
        raise TwitchError(f"Twitch: error {r.status_code}")
    return "Twitch keys work"


async def _game_id(http, name: str) -> str | None:
    data = await _get(http, "search/categories", query=name, first=1)
    items = data.get("data", [])
    return items[0]["id"] if items and items[0]["name"].lower().startswith(name.lower()[:4]) else None


async def _live(http, language: str, game_id: str | None = None) -> list[str]:
    params = {"language": language, "first": 100}
    if game_id:
        params["game_id"] = game_id
    return [s["user_id"] for s in (await _get(http, "streams", **params)).get("data", [])]


async def _channels(http, query: str, language: str) -> list[str]:
    data = await _get(http, "search/channels", query=query, first=100)
    return [c["id"] for c in data.get("data", []) if (c.get("broadcaster_language") or "")[:2] == language]


async def _followers(http, user_id: str) -> int | None:
    try:
        return (await _get(http, "channels/followers", broadcaster_id=user_id, first=1)).get("total")
    except TwitchError:
        return None


async def _videos(http, user_id: str) -> list[dict]:
    try:
        return (await _get(http, "videos", user_id=user_id, first=20, sort="time")).get("data", [])
    except TwitchError:
        return []


def _thumb(url: str) -> str | None:
    return url.replace("%{width}", "320").replace("%{height}", "180") if url else None


def to_creator(user: dict, followers: int | None, language: str, videos: list[dict], found_via: str) -> dict:
    login = user["login"]
    return {
        "id": f"tw_{login}",
        "platform": "twitch",
        "handle": login,
        "name": user.get("display_name") or login,
        "url": f"https://www.twitch.tv/{login}",
        "avatar_src": user.get("profile_image_url"),
        "cover_src": user.get("offline_image_url") or user.get("profile_image_url"),
        "bio": user.get("description") or "",
        "bio_link": None,
        "country": "",
        "language": (language or "")[:2].lower(),
        "followers": followers,
        "posts_count": None,
        "verified": user.get("broadcaster_type") == "partner",
        "recent_posts": [{
            "title": v.get("title") or "",
            "url": v.get("url"),
            "thumb_src": _thumb(v.get("thumbnail_url") or ""),
            "views": v.get("view_count"),
            "likes": None,
            "comments": None,
            "date": v.get("created_at"),
            "is_short": False,
        } for v in videos],
        "found_via": [found_via],
        "_contact_text": user.get("description") or "",
    }


async def _users(http, ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 100):
        out += (await _get(http, "users", id=ids[i:i + 100])).get("data", [])
    return out


async def _build(http, users: list[dict], languages: dict[str, str], via: dict[str, str], fmin, fmax) -> list[dict]:
    follows = await asyncio.gather(*(_followers(http, u["id"]) for u in users))
    keep = [(u, f) for u, f in zip(users, follows) if in_range(f, fmin, fmax)]
    videos = await asyncio.gather(*(_videos(http, u["id"]) for u, _ in keep))
    return [to_creator(u, f, languages.get(u["id"], ""), v, via.get(u["id"], "Twitch")) for (u, f), v in zip(keep, videos)]


async def discover(http, terms: list[str], market: str, language: str, fmin, fmax, max_channels: int = 30) -> list[dict]:
    """Streamers in the market's language: live now (overall and per game), and channels matching the terms."""
    games = await asyncio.gather(*(_game_id(http, t) for t in terms[:6]), return_exceptions=True)
    tasks, labels = [_live(http, language)], [f"Live on Twitch in {language.upper()} ({market})"]
    for t, g in zip(terms, games):
        if isinstance(g, str):
            tasks.append(_live(http, language, g))
            labels.append(f"Live on Twitch: {t} in {language.upper()} ({market})")
        tasks.append(_channels(http, t, language))
        labels.append(f"Twitch channel search “{t}” ({market})")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    if errors and len(errors) == len(results):
        raise errors[0]
    via: dict[str, str] = {}
    for rank in range(100):  # round-robin so every search contributes its best channels
        for label, ids in zip(labels, results):
            if not isinstance(ids, Exception) and rank < len(ids):
                via.setdefault(ids[rank], label)
    users = await _users(http, list(via)[:max_channels * 3])
    creators = await _build(http, users, {u["id"]: language for u in users}, via, fmin, fmax)
    return creators[:max_channels]


async def lookup_logins(http, logins: list[str], label: str) -> list[dict]:
    """Full records for known Twitch names (e.g. a Twitch linked from a YouTube channel, or a tracker row)."""
    data = await _get(http, "users", login=[x.lstrip("@").lower() for x in logins[:100]])
    users = data.get("data", [])
    if not users:
        return []
    channels = await _get(http, "channels", broadcaster_id=[u["id"] for u in users])
    languages = {c["broadcaster_id"]: c.get("broadcaster_language") or "" for c in channels.get("data", [])}
    return await _build(http, users, languages, {u["id"]: label for u in users}, None, None)
