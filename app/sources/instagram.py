"""Instagram discovery via Apify: hashtag posts -> post owners -> profile details."""
from collections import Counter

from .. import config
from ..metrics import in_range
from .apify import run_actor


def _num(value):
    return value if isinstance(value, (int, float)) and value >= 0 else None  # IG reports hidden likes as -1


def _to_creator(p: dict, found_via: str) -> dict:
    username = p["username"]
    posts = []
    for x in (p.get("latestPosts") or [])[:12]:
        url = x.get("url") or (f"https://www.instagram.com/p/{x['shortCode']}/" if x.get("shortCode") else None)
        posts.append({
            "title": (x.get("caption") or "")[:300],
            "url": url,
            "thumb_src": x.get("displayUrl"),
            "views": _num(x.get("videoViewCount") or x.get("videoPlayCount")),
            "likes": _num(x.get("likesCount")),
            "comments": _num(x.get("commentsCount")),
            "date": x.get("timestamp"),
            "pinned": bool(x.get("isPinned")),
        })
    posts.sort(key=lambda q: q.get("date") or "", reverse=True)
    avatar = p.get("profilePicUrlHD") or p.get("profilePicUrl")
    cover = next((q["thumb_src"] for q in posts if q.get("thumb_src") and not q["pinned"]), None)
    return {
        "id": f"ig_{username.lower()}",
        "platform": "instagram",
        "handle": "@" + username,
        "name": p.get("fullName") or username,
        "url": f"https://www.instagram.com/{username}/",
        "avatar_src": avatar,
        "cover_src": cover or avatar,
        "bio": p.get("biography") or "",
        "bio_link": p.get("externalUrl"),
        "public_email": p.get("publicEmail") or p.get("businessEmail") or p.get("email"),
        "category": p.get("businessCategoryName"),
        "country": "",
        "language": "",
        "followers": _num(p.get("followersCount")),
        "posts_count": _num(p.get("postsCount")),
        "verified": bool(p.get("verified")),
        "recent_posts": posts,
        "found_via": [found_via],
    }


async def _profiles(http, usernames: list[str]) -> list[dict]:
    return await run_actor(http, config.APIFY_IG_PROFILE_ACTOR, {"usernames": usernames}, max_items=len(usernames))


async def discover(http, hashtags: list[str], market: str, fmin, fmax,
                   per_tag: int = 30, max_profiles: int = 25) -> list[dict]:
    label = f"Instagram hashtags ({market}): " + ", ".join("#" + h for h in hashtags)
    items = await run_actor(http, config.APIFY_IG_HASHTAG_ACTOR, {"hashtags": hashtags, "resultsLimit": per_tag},
                            max_items=len(hashtags) * per_tag)
    owners = Counter(i["ownerUsername"] for i in items if i.get("ownerUsername"))
    chosen = [u for u, _ in owners.most_common(max_profiles)]
    if not chosen:
        return []
    profiles = await _profiles(http, chosen)
    return [
        _to_creator(p, label) for p in profiles
        if p.get("username") and in_range(_num(p.get("followersCount")), fmin, fmax)
    ]


async def lookup_handles(http, handles: list[str], label: str) -> list[dict]:
    profiles = await _profiles(http, [h.lstrip("@") for h in handles])
    return [_to_creator(p, label) for p in profiles if p.get("username")]
