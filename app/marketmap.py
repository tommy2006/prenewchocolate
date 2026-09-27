"""Market map: what Scout has found in each market, to decide where to go next and what it costs there.

Per market (the creator's country; when that's unknown, the one market their search targeted): how many creators by
size, hidden gems, past partners, how many have an email, typical views and price, the games that dominate and the
best matches. From the library only: creators with 1,000+ followers that nobody marked "not a fit".
"""
import re
import statistics
from collections import Counter

from . import partners
from .config import MIN_FOLLOWERS
from .markets import MARKETS, PLATFORMS

SIZES = ("nano", "micro", "mid", "macro")


def _market(c: dict, m: dict) -> str:
    country = m.get("country") or c.get("country") or ""
    if country:
        return country
    searched = m.get("search_markets") or []
    return searched[0] if len(searched) == 1 else ""


def _median(values: list[float]) -> int | None:
    values = [v for v in values if v]
    return round(statistics.median(values)) if values else None


def build(company: dict, creators: dict[str, dict], matches: dict[str, dict]) -> list[dict]:
    idx = partners.index(company)
    groups: dict[str, list[tuple[dict, dict]]] = {}
    for cid, m in matches.items():
        c = creators.get(cid)
        if not c or m.get("status") == "hidden" or (c.get("followers") or 0) < MIN_FOLLOWERS:
            continue
        groups.setdefault(_market(c, m), []).append((c, m))
    out = []
    for code, rows in groups.items():
        sizes = Counter(c.get("tier") for c, _ in rows)
        prices = [(c["price"]["low"] + c["price"]["high"]) / 2 for c, _ in rows if c.get("price")]
        best, names = [], set()
        for c, m in sorted(rows, key=lambda cm: -cm[1]["score"]):  # one entry per person (YouTube and TikTok)
            key = re.sub(r"[^a-z0-9]", "", (c.get("name") or "").lower()) or c["id"]
            if key not in names:
                names.add(key)
                best.append((c, m))
            if len(best) == 3:
                break
        out.append({
            "market": code,
            "name": MARKETS.get(code, {}).get("name", code) if code else "Unknown country",
            "creators": len(rows),
            "sizes": {s: sizes.get(s, 0) for s in SIZES},
            "platforms": dict(Counter(PLATFORMS.get(c["platform"], c["platform"]) for c, _ in rows).most_common()),
            "hidden_gems": sum(1 for _, m in rows if m.get("hidden_gem")),
            "past_partners": sum(1 for c, m in rows if partners.find(idx, c, m)),
            "with_email": sum(1 for c, _ in rows if c.get("emails")),
            "good_fit": sum(1 for _, m in rows if (m.get("fit") or 0) >= 70),
            "median_views": _median([c.get("median_views") or c.get("avg_views") for c, _ in rows]),
            "median_price": _median(prices),
            "games": [g for g, _ in Counter(g for _, m in rows for g in (m.get("games") or [])[:2]).most_common(3)],
            "best": [{"id": c["id"], "name": c.get("name"), "score": m["score"], "fit": m.get("fit")} for c, m in best],
        })
    # Known markets first, biggest first; the unknown-country bucket last.
    return sorted(out, key=lambda r: (r["market"] == "", -r["creators"]))
