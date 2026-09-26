"""TikTok discovery via the Apify TikTok scraper (search/hashtags -> profile pass for recent videos)."""
from datetime import datetime, timezone

from .. import config
from ..metrics import in_range
from .apify import ApifyError, run_actor

NO_DOWNLOADS = {
    "shouldDownloadVideos": False,
    "shouldDownloadCovers": False,
    "shouldDownloadSubtitles": False,
    "shouldDownloadSlideshowImages": False,
    "shouldDownloadAvatars": False,
}


def _author(item: dict) -> dict:
    return item.get("authorMeta") or item.get("author") or {}


def _handle(author: dict) -> str:
    return (author.get("name") or author.get("uniqueId") or "").lstrip("@")


def _followers(author: dict):
    return author.get("fans") if author.get("fans") is not None else author.get("followerCount")


def _post(item: dict) -> dict:
    created = item.get("createTimeISO")
    if not created and item.get("createTime"):
        created = datetime.fromtimestamp(int(item["createTime"]), timezone.utc).isoformat()
    meta = item.get("videoMeta") or {}
    return {
        "title": (item.get("text") or "")[:300],
        "url": item.get("webVideoUrl"),
        "thumb_src": meta.get("coverUrl") or meta.get("originalCoverUrl"),
        "views": item.get("playCount"),
        "likes": item.get("diggCount"),
        "comments": item.get("commentCount"),
        "date": created,
        "pinned": bool(item.get("isPinned")),
    }


def _group(items: list[dict]) -> dict[str, dict]:
    groups: dict[str, dict] = {}
    for item in items:
        author = _author(item)
        handle = _handle(author)
        if not handle:
            continue
        g = groups.setdefault(handle.lower(), {"author": author, "posts": []})
        if (_followers(author) or 0) > (_followers(g["author"]) or 0):
            g["author"] = author
        g["posts"].append(_post(item))
    return groups


def _to_creator(group: dict, found_via: str) -> dict:
    a = group["author"]
    handle = _handle(a)
    posts = sorted(group["posts"], key=lambda p: p.get("date") or "", reverse=True)
    unpinned = [p for p in posts if not p["pinned"]]
    cover = next((p["thumb_src"] for p in (unpinned or posts) if p.get("thumb_src")), None)
    bio_link = a.get("bioLink")
    if isinstance(bio_link, dict):
        bio_link = bio_link.get("link")
    return {
        "id": f"tt_{handle.lower()}",
        "platform": "tiktok",
        "handle": "@" + handle,
        "name": a.get("nickName") or a.get("nickname") or handle,
        "url": f"https://www.tiktok.com/@{handle}",
        "avatar_src": a.get("avatar") or a.get("originalAvatarUrl"),
        "cover_src": cover or a.get("avatar"),
        "bio": a.get("signature") or "",
        "bio_link": bio_link,
        "country": (a.get("region") or "").upper()[:2],
        "language": "",
        "followers": _followers(a),
        "posts_count": a.get("video") if a.get("video") is not None else a.get("videoCount"),
        "verified": bool(a.get("verified")),
        "recent_posts": posts[:20],
        "found_via": [found_via],
    }


async def _profiles(http, handles: list[str], per_profile: int = 12) -> dict[str, dict]:
    # 12 recent videos: enough for a 30-day (or 90-day) average views window for most creators.
    items = await run_actor(http, config.APIFY_TIKTOK_ACTOR, {
        "profiles": handles, "resultsPerPage": per_profile, **NO_DOWNLOADS,
    }, max_items=len(handles) * per_profile)
    return _group(items)


async def discover(http, queries: list[str], hashtags: list[str], market: str, fmin, fmax,
                   per_query: int = 15, max_profiles: int = 20) -> list[dict]:
    label = f"TikTok search ({market}): " + ", ".join(queries + ["#" + h for h in hashtags])
    items = await run_actor(http, config.APIFY_TIKTOK_ACTOR, {
        "searchQueries": queries, "hashtags": hashtags, "resultsPerPage": per_query, **NO_DOWNLOADS,
    }, max_items=(len(queries) + len(hashtags)) * per_query)
    groups = {h: g for h, g in _group(items).items() if in_range(_followers(g["author"]), fmin, fmax)}

    # Rank by likes-per-follower on the videos we already have before paying for a profile pass.
    def signal(g):
        likes = sum(p.get("likes") or 0 for p in g["posts"]) / max(1, len(g["posts"]))
        return likes / max(1, _followers(g["author"]) or 1)

    chosen = sorted(groups, key=lambda h: signal(groups[h]), reverse=True)[:max_profiles]
    if not chosen:
        return []
    try:
        detailed = await _profiles(http, [_handle(groups[h]["author"]) for h in chosen])
    except ApifyError:
        detailed = {}  # fall back to the search-sample videos
    return [_to_creator(detailed.get(h) or groups[h], label) for h in chosen]


async def lookup_handles(http, handles: list[str], label: str) -> list[dict]:
    groups = await _profiles(http, [h.lstrip("@") for h in handles])
    return [_to_creator(g, label) for g in groups.values()]
