"""What the company's past partners have in common, and how much any other creator is like them.

The examples are the partners from the collaboration tracker that Scout found (Look up & complete, or found by a
search). Each creator is compared with each partner on what a marketer compares: platform, games or niche, market,
size (followers and typical views, on a log scale), engagement for their size and posting rhythm. The score is the
similarity to the three closest partners, and it names them, so it explains itself: "Like Kakkuh and Jyksedi:
Minecraft, Finland, a similar size".

It stays apart from Fit on purpose. Fit judges a creator on its own merits for the brand; this says "you've worked
with creators like this before", which is a different signal (and keeps the blind-search proof honest).
"""
import math
import statistics
from collections import Counter

from . import partners
from .markets import LANGUAGES, MARKETS, PLATFORMS
from .metrics import content_format

WEIGHTS = {"content": 0.32, "market": 0.2, "platform": 0.1, "size": 0.18, "views": 0.1, "rhythm": 0.1}
NEIGHBOURS = 3


def partner_creators(company: dict, creators: dict[str, dict], matches: dict[str, dict]) -> list[tuple[str, dict, dict]]:
    """(partner name, creator, match) for every profile Scout has of a past partner."""
    out, seen = [], set()
    lookup = ((company.get("partners") or {}).get("lookup") or {}).get("results") or {}
    for name, r in lookup.items():
        for cid in r.get("ids", []):
            if cid in creators and cid in matches and cid not in seen:
                seen.add(cid)
                out.append((name, creators[cid], matches[cid]))
    idx = partners.index(company)
    for cid, m in matches.items():
        c = creators.get(cid)
        if c and cid not in seen:
            p = partners.find(idx, c, m)
            if p:
                seen.add(cid)
                out.append((p["name"], c, m))
    return out


def _log(v) -> float | None:
    return math.log10(v) if isinstance(v, (int, float)) and v > 0 else None


def features(c: dict, m: dict) -> dict:
    games = {g.lower() for g in (m.get("games") or [])[:4]}
    return {
        "platform": c["platform"],
        "games": games,
        "niche": (m.get("niche") or "").lower(),
        "market": m.get("country") or c.get("country") or "",
        "language": m.get("language") or c.get("language") or "",
        "followers": _log(c.get("followers")),
        "views": _log(c.get("median_views") or c.get("avg_views")),
        "engagement": math.log2(c["engagement_vs_typical"]) if (c.get("engagement_vs_typical") or 0) > 0 else None,
        "ppm": c.get("posts_per_month"),
        "format": content_format(c),
    }


def _close(a, b, scale: float) -> float | None:
    """1 when equal, falling off with the distance (in log units for sizes)."""
    if a is None or b is None:
        return None
    return math.exp(-abs(a - b) / scale)


def similarity(x: dict, p: dict) -> tuple[float, list[str]]:
    """0-1, and what they share (for the reasons)."""
    shared, parts = [], {}
    common = x["games"] & p["games"]
    if x["games"] and p["games"]:
        # Overlap, not Jaccard: a Minecraft creator is like a partner who plays Minecraft and Fortnite.
        parts["content"] = len(common) / min(len(x["games"]), len(p["games"]))
        if common:
            shared.append(", ".join(sorted(g.title() for g in common)[:2]))
    elif x["niche"] and p["niche"]:
        parts["content"] = 0.6 if x["niche"] == p["niche"] else 0.1
        if x["niche"] == p["niche"]:
            shared.append(x["niche"].title())
    if x["market"] and p["market"]:
        parts["market"] = 1.0 if x["market"] == p["market"] else 0.15
        if x["market"] == p["market"]:
            shared.append(MARKETS.get(x["market"], {}).get("name", x["market"]))
    elif x["language"] and p["language"]:
        parts["market"] = 0.8 if x["language"] == p["language"] and x["language"] != "en" else 0.3
        if parts["market"] >= 0.8:
            shared.append(f"posts in {LANGUAGES.get(x['language'], x['language'])}")
    parts["platform"] = 1.0 if x["platform"] == p["platform"] else 0.3 if x["format"] == p["format"] else 0.0
    if x["platform"] == p["platform"]:
        shared.append(PLATFORMS.get(x["platform"], x["platform"]))
    size = _close(x["followers"], p["followers"], 0.45)
    if size is not None:
        parts["size"] = size
        if size >= 0.6:
            shared.append("a similar size")
    views = _close(x["views"], p["views"], 0.45)
    if views is not None:
        parts["views"] = views
    rhythm = [v for v in (_close(x["engagement"], p["engagement"], 1.0),
                          _close(math.log2((x["ppm"] or 0) + 1) if x["ppm"] is not None else None,
                                 math.log2((p["ppm"] or 0) + 1) if p["ppm"] is not None else None, 1.0)) if v is not None]
    if rhythm:
        parts["rhythm"] = sum(rhythm) / len(rhythm)
    # Missing information counts as "unknown", not as different: a middling 0.5.
    total = sum(WEIGHTS[k] * parts.get(k, 0.5) for k in WEIGHTS)
    return total, shared


class Model:
    """Built once per request from the company's partners; scores any creator against them."""

    def __init__(self, company: dict, creators: dict[str, dict], matches: dict[str, dict]):
        self.examples = [(name, c, features(c, m), c["id"]) for name, c, m in partner_creators(company, creators, matches)]

    def __bool__(self) -> bool:
        return len(self.examples) >= 3

    def score(self, c: dict, m: dict) -> dict | None:
        if not self:
            return None
        x = features(c, m)
        sims = []
        for name, pc, pf, pid in self.examples:
            if pid == c["id"]:
                continue  # a partner isn't compared with itself
            s, shared = similarity(x, pf)
            sims.append((s, name, shared))
        if not sims:
            return None
        sims.sort(key=lambda t: -t[0])
        top = sims[:NEIGHBOURS]
        score = round(100 * sum(s for s, _, _ in top) / len(top))
        names = list(dict.fromkeys(n for _, n, _ in top))[:2]
        return {"score": score, "like": names, "shared": top[0][2][:3]}


def card_value(model: Model, c: dict, m: dict) -> dict | None:
    r = model.score(c, m) if model else None
    return {"score": r["score"], "like": r["like"]} if r else None


def detail_value(model: Model, c: dict, m: dict) -> dict | None:
    r = model.score(c, m) if model else None
    if not r:
        return None
    return {"score": r["score"], "like": r["like"],
            "why": f"Like {' and '.join(r['like'])}" + (f": {', '.join(r['shared'])}" if r["shared"] else "")}


def _quartiles(values: list[float]) -> list[int] | None:
    values = sorted(v for v in values if v)
    if len(values) < 2:
        return [round(values[0])] * 3 if values else None
    q = statistics.quantiles(values, n=4, method="inclusive")
    return [round(q[0]), round(statistics.median(values)), round(q[2])]


def profile(company: dict, creators: dict[str, dict], matches: dict[str, dict]) -> dict:
    """What the past partners Scout found have in common, in numbers a marketer reads at a glance."""
    ex = partner_creators(company, creators, matches)
    if not ex:
        return {"partners": 0}
    names = {n for n, _, _ in ex}
    by_platform = Counter(PLATFORMS.get(c["platform"], c["platform"]) for _, c, _ in ex)
    games = Counter(g for _, _, m in ex for g in (m.get("games") or [])[:3])
    niches = Counter((m.get("niche") or "") for _, _, m in ex if m.get("niche"))
    markets = Counter((m.get("country") or c.get("country") or "") for _, c, m in ex)
    markets.pop("", None)
    sizes = {}
    for plat in ("youtube", "tiktok", "twitch"):
        q = _quartiles([c.get("followers") for _, c, _ in ex if c["platform"] == plat])
        if q:
            sizes[PLATFORMS[plat]] = q
    views = _quartiles([c.get("median_views") or c.get("avg_views") for _, c, _ in ex])
    ppm = [c["posts_per_month"] for _, c, _ in ex if c.get("posts_per_month") is not None]
    sponsored = sum(1 for _, c, _ in ex if max((c.get("sponsorship") or {}).get("sponsored", 0), (c.get("sponsorship") or {}).get("with_codes", 0)))
    top_games = [g for g, _ in games.most_common(4)]
    top_markets = [MARKETS.get(k, {}).get("name", k) for k, _ in markets.most_common(4)]
    plats = [p for p, _ in by_platform.most_common(2)]
    size_text = "; ".join(f"{p} {_short(q[0])}" + (f"–{_short(q[2])}" if q[2] != q[0] else "") for p, q in sizes.items())
    summary = (f"Mostly {' and '.join(plats)} creators"
               + (f" playing {', '.join(top_games[:3])}" if top_games else "")
               + (f", in {', '.join(top_markets[:3])}" if top_markets else "")
               + (f"; typical size {size_text}" if size_text else "")
               + (f"; posting about {statistics.median(ppm):.0f} times a month" if ppm else "") + ".")
    return {
        "partners": len(names),
        "profiles": len(ex),
        "summary": summary,
        "platforms": dict(by_platform.most_common()),
        "games": dict(games.most_common(6)),
        "niches": dict(niches.most_common(4)),
        "markets": {MARKETS.get(k, {}).get("name", k): n for k, n in markets.most_common(6)},
        "followers": sizes,  # platform -> [25th percentile, median, 75th percentile]
        "median_views": views,
        "posts_per_month": round(statistics.median(ppm), 1) if ppm else None,
        "sponsor_experience": round(sponsored / len(ex), 2),
    }


def _short(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)
