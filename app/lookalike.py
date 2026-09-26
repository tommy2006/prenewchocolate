"""Find more like these: start from creators the company knows (past partners, creators it likes, or one
from the results) and collect the creators *they* point to. Creators @mention friends and collab partners in
their videos and feature them on their channel page, and those are usually the same kind of local creator
in the same niche. One hop only; the usual filters (size, activity, market) and scoring then apply.
"""
import asyncio
import re

from . import linking
from .metrics import in_range, mentions_in
from .sources import tiktok, youtube


NOT_CREATORS = {"youtube", "tiktok", "instagram", "twitch", "gmail", "hotmail", "outlook", "everyone", "here"}
MAX_PER_PLATFORM = 40  # profiles fetched per platform (YouTube: about 3 quota units each)


def mentions(c: dict) -> list[str]:
    """Who a creator @mentions in their recent posts (saved when they were fetched; older records: read from
    their post titles). Not the bio: that's usually their own other accounts or management."""
    own = {(c.get("handle") or "").lstrip("@").lower()}
    own |= {linking.lookup_handle(k).lstrip("@").lower() for k in
            (linking.url_key(n, u) for n, u in (c.get("socials") or {}).items()) if k}
    found = list(c.get("mentions") or [])
    found += mentions_in(c.get("handle") or "", *(f"{p.get('title') or ''} {p.get('desc') or ''}" for p in c.get("recent_posts", [])))
    return [h for h in dict.fromkeys(found) if h not in own and h not in NOT_CREATORS]


def _name(c: dict) -> str:
    return c.get("name") or (c.get("handle") or "").lstrip("@") or c["id"]


async def related(http, seeds: list[dict], platforms: list[str], known: set[str]) -> tuple[dict, dict]:
    """(YouTube channel id -> found via, TikTok handle -> found via) for creators the seeds point to."""
    yt_ids: dict[str, str] = {}
    yt_handles: dict[str, str] = {}
    tt_handles: dict[str, str] = {}
    for s in seeds:
        for h in mentions(s):
            target = tt_handles if s["platform"] == "tiktok" else yt_handles
            target.setdefault(h, f"Mentioned by {_name(s)}")
    if "youtube" in platforms:
        yt_seeds = [s for s in seeds if s["platform"] == "youtube" and s["id"].startswith("yt_")]
        featured = await asyncio.gather(*(youtube.featured_channels(http, s["id"][3:]) for s in yt_seeds),
                                        return_exceptions=True)
        for s, ids in zip(yt_seeds, featured):
            for cid in ids if isinstance(ids, list) else []:
                yt_ids.setdefault(cid, f"Featured on {_name(s)}'s channel")
        # @handles from YouTube descriptions: look up which are YouTube channels (1 quota unit each)
        todo = [h for h in yt_handles if f"youtube:@{h}" not in known][:MAX_PER_PLATFORM]
        channels = await asyncio.gather(*(youtube.channel_by_handle(http, h) for h in todo), return_exceptions=True)
        for h, ch in zip(todo, channels):
            if isinstance(ch, dict):
                yt_ids.setdefault(ch["id"], yt_handles[h])
    seed_ids = {s["id"] for s in seeds}
    yt_ids = {cid: via for cid, via in yt_ids.items() if f"yt_{cid}" not in seed_ids and f"youtube:{cid}" not in known}
    tt_handles = {h: via for h, via in tt_handles.items() if f"tt_{h}" not in seed_ids and f"tiktok:{h}" not in known}
    return yt_ids, tt_handles


async def expand(http, seeds: list[dict], platforms: list[str], size_of, known: set[str]) -> list[dict]:
    """Full records of the creators the seeds point to, inside each platform's size range."""
    yt_ids, tt_handles = await related(http, seeds, platforms, known)
    out = []
    if "youtube" in platforms and yt_ids:
        channels = await youtube.fetch_channels(http, list(yt_ids)[:MAX_PER_PLATFORM * 2])
        lo, hi = size_of("youtube")
        keep = [ch for ch in channels if in_range(youtube.subscribers(ch), lo, hi)][:MAX_PER_PLATFORM]
        out += await youtube.build(http, keep, {ch["id"]: yt_ids[ch["id"]] for ch in keep})
    if "tiktok" in platforms and tt_handles:
        quick = [c for c in await asyncio.gather(*(tiktok.profile(http, h) for h in list(tt_handles)[:MAX_PER_PLATFORM])) if c]
        lo, hi = size_of("tiktok")
        quick = [c for c in quick if in_range(c.get("followers"), lo, hi)]
        for c in await tiktok.complete(http, quick, "Mentioned by a creator you know"):
            c["found_via"] = [tt_handles.get(c["handle"].lstrip("@").lower(), c["found_via"][0])]
            out.append(c)
    return out


async def seeds_from_handles(http, raw: list[str], status: dict) -> list[dict]:
    """"Creators you already like" as typed: profile links, or @handles (tried on TikTok and YouTube)."""
    tt, yt = [], []
    for text in raw:
        text = text.strip()
        keys = [k for k in (linking.url_key(n, text) for n in ("youtube", "tiktok")) if k]
        if keys:
            for k in keys:
                (yt if k.startswith("youtube:") else tt).append(linking.lookup_handle(k))
        elif re.fullmatch(r"@?[\w.\-]{2,30}", text):
            tt.append(text.lstrip("@"))
            yt.append("@" + text.lstrip("@"))
    out = []
    if tt and status.get("tiktok"):
        out += await tiktok.lookup_handles(http, list(dict.fromkeys(tt)), "A creator you like")
    if yt and status.get("youtube"):
        ids = []
        for h in dict.fromkeys(yt):
            if h.startswith("UC") and len(h) == 24:
                ids.append(h)
            else:
                ch = await youtube.channel_by_handle(http, h)
                if ch:
                    ids.append(ch["id"])
        if ids:
            channels = await youtube.fetch_channels(http, ids)
            out += await youtube.build(http, channels, {ch["id"]: "A creator you like" for ch in channels})
    return out


def seed_label(seeds: list[dict], limit: int = 3) -> str:
    names = list(dict.fromkeys(_name(s) for s in seeds))  # someone on YouTube and TikTok counts once
    return ", ".join(names[:limit]) + (f" and {len(names) - limit} more" if len(names) > limit else "")
