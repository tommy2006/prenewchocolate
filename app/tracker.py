"""Find the creators in the company's collaboration tracker on YouTube and TikTok, by name.

The tracker has names ("Mr Rockis", "Steven Erixon (Stevenson)") and sometimes their size, but no links.
We try the handles a name suggests (mrrockis, steven_erixon...) and, failing that, a web search for the name.
A profile only counts if it's plausibly the same person: its size is close to what the tracker says, or,
when the tracker has no numbers, the name is distinctive enough and the profile is in the right market.
"""
import asyncio
import logging
import re

from . import partners
from .markets import MARKETS
from .sources import tiktok, twitch, websearch, youtube

log = logging.getLogger("scout")

LABEL = "Your collaboration tracker"  # found_via for profiles found this way (not by Scout's own searches)
MAX_GUESSES = 5
SIZE_RATIO = 3.0  # followers may have grown or shrunk since: accept a third to three times the tracker's number
MIN_UNIQUE = 6  # without numbers to compare, a handle needs at least this many letters to be trusted


def handle_guesses(p: dict) -> list[str]:
    """"Mr Rockis" -> mrrockis, mr_rockis, mr.rockis; "Memetix_swe" -> memetix_swe, memetixswe..."""
    out = []
    for raw in [*p.get("channels", []), p["name"]]:
        for part in [raw, *re.split(r"[+&/,()]| and ", raw)]:
            words = re.findall(r"[\w.\-]+", part.lower())
            if not words:
                continue
            for joiner in ("", "_", "."):
                h = joiner.join(words).strip("._-")
                if 3 <= len(h) <= 30 and re.fullmatch(r"[a-z0-9_.\-]+", h) and h not in out:
                    out.append(h)
    return out[:MAX_GUESSES]


def platforms_to_try(p: dict) -> list[str]:
    """YouTube and/or TikTok: what the tracker says they're on, or both when it doesn't say."""
    said = " ".join(p.get("platforms", [])).lower()
    out = []
    if "youtube" in said or p.get("yt_subs") or not said:
        out.append("youtube")
    if "tiktok" in said or p.get("tt_followers") or not said:
        out.append("tiktok")
    if "twitch" in said:
        out.append("twitch")
    return out


def _expected(p: dict, platform: str) -> int | None:
    return p.get("yt_subs") if platform == "youtube" else p.get("tt_followers")


def plausible(p: dict, platform: str, handle: str, followers: int | None) -> tuple[bool, bool]:
    """(accept, sure). Sure = the size matches the tracker; otherwise only distinctive names are accepted."""
    expected = _expected(p, platform)
    if expected and followers:
        ok = expected / SIZE_RATIO <= followers <= expected * SIZE_RATIO
        return ok, ok
    return len(partners.norm(handle)) >= MIN_UNIQUE, False


def _outside(c: dict, market: str) -> bool:
    """Clearly based in another market (only used when we couldn't check the size)."""
    if not market or market not in MARKETS:
        return False
    langs = set(MARKETS[market]["languages"])
    country, lang = c.get("country") or "", c.get("language") or ""
    return bool((country and country != market) or (lang and lang != "en" and lang not in langs))


async def _youtube(http, p: dict, guesses: list[str]) -> tuple[dict | None, bool, str]:
    for g in guesses:
        channel = await youtube.channel_by_handle(http, g)
        if not channel:
            continue
        ok, sure = plausible(p, "youtube", g, youtube.subscribers(channel))
        if not ok:
            continue
        found = await youtube.build(http, [channel], {channel["id"]: f"{LABEL}: {p['name']}"})
        if found and (sure or not _outside(found[0], p.get("market", ""))):
            return found[0], sure, g
    return None, False, ""


async def _tiktok(http, p: dict, guesses: list[str]) -> tuple[dict | None, bool, str]:
    for g in guesses:
        quick = await tiktok.profile(http, g)
        if not quick:
            continue
        ok, sure = plausible(p, "tiktok", g, quick.get("followers"))
        if not ok:
            continue
        found = await tiktok.complete(http, [quick], f"{LABEL}: {p['name']}")
        if found and (sure or not _outside(found[0], p.get("market", ""))):
            return found[0], sure, g
    return None, False, ""


async def _twitch(http, p: dict, guesses: list[str]) -> tuple[dict | None, bool, str]:
    found = {c["handle"]: c for c in await twitch.lookup_logins(http, guesses, f"{LABEL}: {p['name']}")}
    for g in guesses:  # the tracker has no Twitch numbers: only distinctive names in the right market count
        c = found.get(g)
        if c and plausible(p, "twitch", g, c.get("followers"))[0] and not _outside(c, p.get("market", "")):
            return c, False, g
    return None, False, ""


def _web_guesses(p: dict, handles: list[str], tried: list[str]) -> list[str]:
    """Handles from a web search for the name, kept only when they contain the name's longest word."""
    words = sorted((partners.norm(w) for w in re.findall(r"\w{4,}", p["name"])), key=len, reverse=True)
    key = words[0] if words else partners.norm(p["name"])
    return [h for h in handles if key and key in partners.norm(h) and h not in tried][:3]


async def resolve(http, p: dict, status: dict) -> dict:
    """One tracker entry -> {"status": found | not_found | twitch | no_source, "profiles": [...], "sure", "how"}."""
    wanted = [pl for pl in platforms_to_try(p) if status.get(pl)]
    said = " ".join(p.get("platforms", [])).lower()
    if not wanted:  # e.g. a Twitch streamer while Twitch isn't set up
        return {"status": "twitch" if "twitch" in said else "no_source", "profiles": [], "sure": False, "how": ""}
    guesses = handle_guesses(p)
    lookups = {"youtube": _youtube, "tiktok": _tiktok, "twitch": _twitch}
    names = {"youtube": "YouTube", "tiktok": "TikTok", "twitch": "Twitch"}
    profiles, sure, how = [], [], []
    for platform in wanted:
        try:
            found, is_sure, handle = await lookups[platform](http, p, guesses)
            if not found:  # the name isn't their handle: ask a search engine for their profile
                market = p.get("market") if p.get("market") in MARKETS else "FI"
                hits = await websearch.search(http, platform, f'"{p["name"]}"', market)
                found, is_sure, handle = await lookups[platform](http, p, _web_guesses(p, hits, guesses))
                if found:
                    how.append(f"{names[platform]} via web search")
            elif handle:
                how.append(f"{names[platform]} @{handle}")
        except Exception as e:  # one platform failing shouldn't lose the other
            log.info("tracker lookup %s on %s failed: %s", p["name"], platform, e)
            continue
        if found:
            profiles.append(found)
            sure.append(is_sure)
    return {"status": "found" if profiles else "not_found", "profiles": profiles,
            "sure": bool(profiles) and all(sure), "how": ", ".join(how)}


async def resolve_all(http, items: list[dict], status: dict, on_progress=None, concurrency: int = 4) -> dict[str, dict]:
    """Every tracker entry, a few at a time. Returns name -> resolve() result."""
    sem = asyncio.Semaphore(concurrency)
    results: dict[str, dict] = {}

    async def one(p):
        async with sem:
            try:
                results[p["name"]] = await resolve(http, p, status)
            except Exception as e:
                log.warning("tracker lookup %s failed: %s", p["name"], e)
                results[p["name"]] = {"status": "not_found", "profiles": [], "sure": False, "how": ""}
        if on_progress:
            on_progress(len(results))

    await asyncio.gather(*(one(p) for p in items))
    return results
