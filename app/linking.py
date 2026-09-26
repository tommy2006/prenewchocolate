"""One person, several platforms: link a creator's YouTube channel, TikTok and Instagram profiles.

Prenew's collaboration tracker has one row per creator with YouTube and TikTok numbers side by side.
Profiles are linked only when one of them links to the other (bio, channel links or video descriptions),
never by name alone, because many creators share a name.
"""
import re

URL_KEYS = {
    "youtube": re.compile(r"youtube\.com/(?:@([\w.\-]+)|channel/(UC[\w\-]{22})|c/([\w.\-]+))", re.I),
    "tiktok": re.compile(r"tiktok\.com/@([\w.\-]+)", re.I),
    "instagram": re.compile(r"instagram\.com/(?!p/|reel/|explore/|stories/)([\w.]+)", re.I),
}


def url_key(network: str, url: str) -> str | None:
    """"youtube:@name", "youtube:UC…" or "tiktok:name" for a profile URL; None if it isn't one."""
    pattern = URL_KEYS.get(network)
    m = pattern.search(url or "") if pattern else None
    if not m:
        return None
    if network == "youtube":
        handle, channel_id, custom = m.groups()
        return f"youtube:{channel_id}" if channel_id else f"youtube:@{(handle or custom).lower()}"
    return f"{network}:{m.group(1).lower().rstrip('.')}"


def own_keys(c: dict) -> list[str]:
    handle = (c.get("handle") or "").lstrip("@").lower()
    keys = [f"youtube:@{handle}" if c["platform"] == "youtube" else f"{c['platform']}:{handle}"] if handle else []
    if c["platform"] == "youtube" and c["id"].startswith("yt_"):
        keys.append(f"youtube:{c['id'][3:]}")
    return keys


def lookup_handle(key: str) -> str:
    """What the platform lookups take: "@name", a channel ID, or a TikTok name."""
    return key.split(":", 1)[1]


def groups(creators: dict[str, dict]) -> dict[str, list[str]]:
    """creator id -> ids of every profile of the same person (itself included)."""
    by_key = {k: cid for cid, c in creators.items() for k in own_keys(c)}
    parent = {cid: cid for cid in creators}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for cid, c in creators.items():
        for network, url in (c.get("socials") or {}).items():
            other = by_key.get(url_key(network, url) or "")
            if other and other != cid:
                parent[find(other)] = find(cid)
    members: dict[str, list[str]] = {}
    for cid in creators:
        members.setdefault(find(cid), []).append(cid)
    return {cid: members[find(cid)] for cid in creators}


def profiles(ids: list[str], creators: dict[str, dict], prefer: set[str] | None = None) -> dict[str, dict]:
    """One profile per platform. If a person has two channels on a platform, keep the ranked one, else the bigger."""
    prefer = prefer or set()
    best: dict[str, dict] = {}
    for cid in ids:
        c = creators[cid]
        cur = best.get(c["platform"])
        rank = (cid in prefer, c.get("followers") or 0)
        if cur is None or rank > (cur["id"] in prefer, cur.get("followers") or 0):
            best[c["platform"]] = c
    return best


def missing_links(c: dict, known: set[str], networks=("youtube", "tiktok")) -> list[tuple[str, str]]:
    """(network, key) for profiles this creator links to whose key isn't in `known` (the library's keys)."""
    out = []
    for network in networks:
        key = url_key(network, (c.get("socials") or {}).get(network, ""))
        if key and key not in known:
            out.append((network, key))
    return out
