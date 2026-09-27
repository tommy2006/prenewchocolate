"""Scout's own TikTok scraper: no Apify, no API key.

1. Find accounts: web search for the planned local-language queries and hashtags (websearch.py).
2. Quick check: TikTok's public profile embed (/embed/@name) gives followers, bio and the latest ~9
   videos with view counts; a video's upload time is encoded in its ID. Accounts outside the size
   range or inactive are dropped here, after one request each.
3. Details for the rest: the profile page (bio link, video count) and a few video pages (likes,
   comments, the country and language TikTok detected, and @mentions).
4. Snowball: creators @mentioned in those videos are often local creators in the same niche,
   which is how small markets are found.

All of these are the public pages anyone can open without logging in. TikTok's own search needs a
login and shows a CAPTCHA to automated browsers, so we don't use it.
"""
import asyncio
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone

import httpx

from ..metrics import in_range
from . import websearch

log = logging.getLogger("scout")
UA = websearch.UA
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
_pages = asyncio.Semaphore(4)
ACTIVE_DAYS = 120
STAT_VIDEOS = 3  # video pages opened per creator for likes/comments
UNIVERSAL = re.compile(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', re.S)
FRONTITY = re.compile(r'<script id="__FRONTITY_CONNECT_STATE__" type="application/json">(.*?)</script>', re.S)


class TikTokBlocked(Exception):
    pass


async def _page(http: httpx.AsyncClient, url: str, pattern: re.Pattern) -> dict | None:
    async with _pages:
        try:
            r = await http.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        except httpx.HTTPError as e:
            log.info("tiktok page %s failed: %s", url, e)
            return None
        await asyncio.sleep(0.25)
    m = pattern.search(r.text) if r.status_code == 200 else None
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _date_from_id(video_id: str) -> str | None:
    """TikTok video IDs start with the upload time: the top 32 bits are Unix seconds."""
    try:
        return datetime.fromtimestamp(int(video_id) >> 32, timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


async def _quick(http, handle: str) -> dict | None:
    """Followers, bio and latest videos with views from the public profile embed (one request)."""
    data = await _page(http, f"https://www.tiktok.com/embed/@{handle}", FRONTITY)
    if not data:
        return None
    pages = (data.get("source") or {}).get("data") or {}
    info = next((v for k, v in pages.items() if k.lower().startswith("/embed/@")), None) or {}
    user = info.get("userInfo") or {}
    if not user.get("uniqueId") or user.get("privateAccount"):
        return None
    name = user["uniqueId"]
    posts = []
    for v in info.get("videoList") or []:
        if not v.get("id"):
            continue
        posts.append({
            "id": v["id"],
            "title": (v.get("desc") or "")[:300],
            "url": f"https://www.tiktok.com/@{name}/video/{v['id']}",
            "thumb_src": v.get("coverUrl") or v.get("originCoverUrl"),
            "views": v.get("playCount"),
            "likes": None,
            "comments": None,
            "date": _date_from_id(v["id"]),
            "pinned": False,
        })
    posts.sort(key=lambda p: p["date"] or "", reverse=True)
    return {
        "id": f"tt_{name.lower()}",
        "platform": "tiktok",
        "handle": "@" + name,
        "name": user.get("nickname") or name,
        "url": f"https://www.tiktok.com/@{name}",
        "avatar_src": user.get("avatarThumbUrl"),
        "cover_src": next((p["thumb_src"] for p in posts if p.get("thumb_src")), None) or user.get("avatarThumbUrl"),
        "bio": user.get("signature") or "",
        "bio_link": None,
        "country": "",
        "language": "",
        "followers": user.get("followerCount"),
        "posts_count": None,
        "verified": bool(user.get("verified")),
        "recent_posts": posts,
    }


def _active(c: dict) -> bool:
    latest = c["recent_posts"][0]["date"] if c["recent_posts"] else None
    if not latest:
        return False
    return (datetime.now(timezone.utc) - datetime.fromisoformat(latest)).days <= ACTIVE_DAYS


def _reach(c: dict) -> float:
    views = [p["views"] for p in c["recent_posts"][:9] if isinstance(p.get("views"), int)]
    return (sorted(views)[len(views) // 2] if views else 0) / max(1, c.get("followers") or 1)


async def _details(http, c: dict) -> dict:
    """Add bio link, video count, likes/comments on a few recent videos, country and language."""
    name = c["handle"].lstrip("@")
    recent = [p for p in c["recent_posts"] if p.get("views")][:STAT_VIDEOS]
    profile, *videos = await asyncio.gather(
        _page(http, f"https://www.tiktok.com/@{name}", UNIVERSAL),
        *(_page(http, p["url"], UNIVERSAL) for p in recent),
    )
    detail = ((profile or {}).get("__DEFAULT_SCOPE__") or {}).get("webapp.user-detail") or {}
    info = detail.get("userInfo") or {}
    user, stats = info.get("user") or {}, info.get("stats") or {}
    link = (user.get("bioLink") or {}).get("link")
    if link and not link.startswith("http"):
        link = "https://" + link
    c["bio_link"] = link
    c["posts_count"] = stats.get("videoCount")
    c["bio"] = user.get("signature") or c["bio"]
    c["verified"] = bool(user.get("verified")) or c["verified"]
    if user.get("avatarLarger"):
        c["avatar_src"] = user["avatarLarger"]

    countries, languages, mentions = Counter(), Counter(), []
    for post, page in zip(recent, videos):
        item = ((((page or {}).get("__DEFAULT_SCOPE__") or {}).get("webapp.video-detail") or {})
                .get("itemInfo") or {}).get("itemStruct") or {}
        st = item.get("stats") or {}
        if not st:
            continue
        post["views"] = st.get("playCount", post["views"])
        post["likes"] = st.get("diggCount")
        post["comments"] = st.get("commentCount")
        if item.get("createTime"):
            post["date"] = datetime.fromtimestamp(int(item["createTime"]), timezone.utc).isoformat(timespec="seconds")
        if item.get("locationCreated"):
            countries[item["locationCreated"].upper()] += 1
        lang = (item.get("textLanguage") or "")[:2].lower()
        if lang and lang != "un":
            languages[lang] += 1
        for extra in item.get("textExtra") or []:
            other = (extra.get("userUniqueId") or "").lower()
            if other and other != name.lower() and other not in mentions:
                mentions.append(other)
    c["country"] = countries.most_common(1)[0][0] if countries else ""
    c["language"] = languages.most_common(1)[0][0] if languages else ""
    c["_mentions"] = mentions
    return c


def _finish(c: dict, label: str) -> dict:
    c["mentions"] = (c.pop("_mentions", None) or [])[:15]  # who they @mention: for "find more like these"
    for p in c["recent_posts"]:
        p.pop("id", None)
    c["recent_posts"] = c["recent_posts"][:20]
    c["found_via"] = [label]
    return c


async def discover(http, queries: list[str], hashtags: list[str], market: str, fmin, fmax,
                   max_profiles: int = 20, per_search: int = 15) -> list[dict]:
    label = f"TikTok via web search ({market}): " + ", ".join(queries + ["#" + h for h in hashtags])
    results = await asyncio.gather(*(websearch.search(http, "tiktok", t, market) for t in queries + hashtags))
    handles = []
    for rank in range(per_search):  # round-robin so every search contributes its best accounts
        for found in results:
            if rank < len(found) and found[rank] not in handles:
                handles.append(found[rank])
    if not handles:
        raise TikTokBlocked("Web search found no TikTok accounts for these searches. Try other words or a bigger market.")

    quick = [c for c in await asyncio.gather(*(_quick(http, h) for h in handles)) if c]
    if not quick:
        raise TikTokBlocked(f"Found {len(handles)} TikTok accounts but TikTok didn't return their profiles. "
                            "It may be limiting requests from this network; try again in a few minutes.")
    keep = sorted((c for c in quick if in_range(c.get("followers"), fmin, fmax) and _active(c)), key=_reach, reverse=True)
    chosen = await asyncio.gather(*(_details(http, c) for c in keep[:max_profiles]))

    # Snowball: accounts these creators @mention are often local creators in the same niche.
    seen = set(handles)
    mentioned = [m for c in chosen for m in c.get("_mentions", []) if m not in seen]
    mentioned = list(dict.fromkeys(mentioned))[:12]
    extra = [c for c in await asyncio.gather(*(_quick(http, h) for h in mentioned)) if c]
    extra = sorted((c for c in extra if in_range(c.get("followers"), fmin, fmax) and _active(c)), key=_reach, reverse=True)[:6]
    extra = await asyncio.gather(*(_details(http, c) for c in extra))
    return [_finish(c, label) for c in chosen] + [_finish(c, f"TikTok: mentioned by creators found in {market}") for c in extra]


async def lookup_handles(http, handles: list[str], label: str) -> list[dict]:
    """Full records for known @handles (a TikTok linked from another profile, a tracker row or a pasted link)."""
    quick = [c for c in await asyncio.gather(*(_quick(http, h.lstrip("@")) for h in handles)) if c]
    return await complete(http, quick, label)


async def profile(http, handle: str) -> dict | None:
    """Followers, bio and latest videos for one @handle (one request). None if there's no such public account."""
    return await _quick(http, handle.lstrip("@"))


async def complete(http, quick: list[dict], label: str) -> list[dict]:
    """Likes, comments, country and language for profiles from profile()."""
    full = await asyncio.gather(*(_details(http, c) for c in quick))
    return [_finish(c, label) for c in full]
