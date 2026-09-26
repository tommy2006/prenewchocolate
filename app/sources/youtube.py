"""YouTube discovery via the official Data API v3.

Quota note: search costs 100 units, everything else 1 unit. The free daily quota is 10,000.
"""
import asyncio
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import httpx

from .. import settings
from ..metrics import in_range

API = "https://www.googleapis.com/youtube/v3"


class YouTubeError(Exception):
    pass


async def _get(http: httpx.AsyncClient, path: str, **params) -> dict:
    params["key"] = settings.youtube_key()
    r = await http.get(f"{API}/{path}", params=params, timeout=30)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = r.text[:200]
        raise YouTubeError(f"YouTube {path}: {msg}")
    return r.json()


async def search_channel_ids(http, query: str, region: str, language: str, max_results: int = 50) -> list[str]:
    """Search recent videos (not channels) so we find people actively making this content."""
    after = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = await _get(
        http, "search", part="snippet", q=query, type="video", maxResults=max_results,
        regionCode=region, relevanceLanguage=language, publishedAfter=after, order="relevance",
    )
    ids = []
    for item in data.get("items", []):
        cid = item.get("snippet", {}).get("channelId")
        if cid and cid not in ids:
            ids.append(cid)
    return ids


async def fetch_channels(http, ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        data = await _get(
            http, "channels", part="snippet,statistics,brandingSettings,contentDetails",
            id=",".join(ids[i:i + 50]), maxResults=50,
        )
        out.extend(data.get("items", []))
    return out


async def fetch_recent_videos(http, uploads_playlist: str, n: int = 30) -> list[dict]:
    """Enough uploads to cover ~90 days for most channels (2 quota units either way)."""
    data = await _get(http, "playlistItems", part="contentDetails", playlistId=uploads_playlist, maxResults=n)
    vids = [it["contentDetails"]["videoId"] for it in data.get("items", []) if it.get("contentDetails")]
    if not vids:
        return []
    return (await _get(http, "videos", part="snippet,statistics,contentDetails", id=",".join(vids))).get("items", [])


DURATION_RE = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def _seconds(iso: str | None) -> int | None:
    m = DURATION_RE.fullmatch(iso or "")
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    total = ((d * 24 + h) * 60 + mi) * 60 + s
    return total or None  # P0D = upcoming premiere or live stream


def _is_short(video: dict) -> bool:
    """Shorts get very different view counts; sponsored integrations run in normal videos."""
    secs = _seconds(video.get("contentDetails", {}).get("duration"))
    sn = video.get("snippet", {})
    text = (sn.get("title", "") + " " + sn.get("description", "")[:300]).lower()
    return secs is not None and (secs <= 60 or (secs <= 180 and "#short" in text))


def _subs(channel: dict) -> int | None:
    st = channel.get("statistics", {})
    if st.get("hiddenSubscriberCount") or "subscriberCount" not in st:
        return None
    return int(st["subscriberCount"])


def _int(value):
    return int(value) if value is not None else None


def to_creator(channel: dict, videos: list[dict], found_via: str) -> dict:
    sn = channel.get("snippet", {})
    st = channel.get("statistics", {})
    branding = channel.get("brandingSettings", {}).get("channel", {})
    thumbs = sn.get("thumbnails", {})
    avatar = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
    handle = sn.get("customUrl") or ""
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    posts = []
    for v in videos:
        vs, vsn = v.get("statistics", {}), v.get("snippet", {})
        vt = vsn.get("thumbnails", {})
        posts.append({
            "title": vsn.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={v['id']}",
            "thumb_src": (vt.get("medium") or vt.get("high") or vt.get("default") or {}).get("url"),
            "views": _int(vs.get("viewCount")),
            "likes": _int(vs.get("likeCount")),
            "comments": _int(vs.get("commentCount")),
            "date": vsn.get("publishedAt"),
            "is_short": _is_short(v),
        })
    posts.sort(key=lambda p: p.get("date") or "", reverse=True)
    # Channels rarely set a language, but most videos carry their audio language: a strong market signal.
    audio = Counter(
        (v.get("snippet", {}).get("defaultAudioLanguage") or v.get("snippet", {}).get("defaultLanguage") or "")[:2].lower()
        for v in videos
    )
    audio.pop("", None)
    channel_lang = (sn.get("defaultLanguage") or branding.get("defaultLanguage") or "")[:2].lower()
    return {
        "id": f"yt_{channel['id']}",
        "platform": "youtube",
        "handle": handle,
        "name": sn.get("title", ""),
        "url": f"https://www.youtube.com/{handle}" if handle else f"https://www.youtube.com/channel/{channel['id']}",
        "avatar_src": avatar,
        "cover_src": avatar,
        "bio": sn.get("description", ""),
        "bio_link": None,
        "country": (sn.get("country") or branding.get("country") or "").upper(),
        "language": audio.most_common(1)[0][0] if audio else channel_lang,
        "followers": _subs(channel),
        "posts_count": _int(st.get("videoCount")),
        "verified": False,
        "recent_posts": posts,
        "found_via": [found_via],
        # Business emails and other socials are often only in video descriptions ("Business: ...").
        # Read by metrics.compute for contact extraction, then dropped.
        "_contact_text": "\n".join(v.get("snippet", {}).get("description", "")[:1500] for v in videos[:15]),
    }


async def _build(http, channels: list[dict], via: dict[str, str]) -> list[dict]:
    uploads = [c.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads") for c in channels]
    videos = await asyncio.gather(
        *(fetch_recent_videos(http, u) if u else asyncio.sleep(0, result=[]) for u in uploads),
        return_exceptions=True,
    )
    creators = []
    for channel, vids in zip(channels, videos):
        if isinstance(vids, Exception):
            vids = []
        creators.append(to_creator(channel, vids, via.get(channel["id"], "YouTube")))
    return creators


async def discover(http, queries: list[str], market: str, language: str, fmin, fmax, max_channels: int = 40) -> list[dict]:
    results = await asyncio.gather(
        *(search_channel_ids(http, q, market, language) for q in queries), return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, Exception)]
    if errors and len(errors) == len(results):
        raise errors[0]
    via: dict[str, str] = {}
    for q, ids in zip(queries, results):
        if isinstance(ids, Exception):
            continue
        for cid in ids:
            via.setdefault(cid, f"YouTube search “{q}” ({market})")
    channels = await fetch_channels(http, list(via))
    channels = [c for c in channels if in_range(_subs(c), fmin, fmax)][:max_channels]
    return await _build(http, channels, via)


async def lookup_handles(http, handles: list[str], label: str) -> list[dict]:
    """Resolve @handles (e.g. from the AI web scout) into full creator records."""
    async def resolve(h):
        data = await _get(http, "channels", part="id", forHandle="@" + h.lstrip("@"))
        items = data.get("items", [])
        return items[0]["id"] if items else None

    ids = await asyncio.gather(*(resolve(h) for h in handles), return_exceptions=True)
    ids = [i for i in ids if isinstance(i, str)]
    if not ids:
        return []
    channels = await fetch_channels(http, ids)
    return await _build(http, channels, {c["id"]: label for c in channels})
