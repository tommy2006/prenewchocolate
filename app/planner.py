"""Campaign planner: the best mix of creators for a budget, from the list the team is looking at.

Each creator is one sponsored post at their typical (median) views and their estimated price. What a post is worth
depends on the campaign goal:
- awareness: its views, counted as far as the audience is real and in the target markets;
- sales: the views of people likely to buy (audience fit, overall fit and authenticity weigh them);
- balanced: its views weighed by the match score.
Creators are picked by value per euro until the budget or the number of creators runs out, one profile per person,
and never someone the team marked "not a fit", who works with a competitor or is a brand-safety risk. Prices and views are estimates from public numbers, so the plan is a
starting point to negotiate from, not a quote.
"""
import re
from collections import Counter

from . import linking
from .markets import MARKETS, PLATFORMS

TIER_NAMES = {"nano": "under 10k", "micro": "10k–50k", "mid": "50k–250k", "macro": "250k+"}


def _worth(c: dict, m: dict, goal: str) -> float:
    views = c.get("median_views") or c.get("avg_views") or 0
    parts = m.get("fit_parts") or {}
    real = ((c.get("authenticity") or {}).get("score") or 70) / 100
    if goal == "awareness":
        return views * real * parts.get("market", 50) / 100
    if goal == "sales":
        return views * real * (parts.get("audience", 50) / 100) * ((m.get("fit") or 50) / 100)
    return views * ((m.get("score") or 50) / 100) ** 2


def plan(rows: list[tuple[dict, dict]], creators: dict[str, dict], budget: int, goal: str, max_creators: int = 12,
         need_email: bool = False, min_fit: int = 55, is_partner=None, new_only: bool = False) -> dict:
    groups = linking.groups(creators)
    candidates, skipped = [], Counter()
    for c, m in rows:
        if m.get("status") in ("hidden", "declined"):
            continue
        if m.get("competitor_sponsor"):
            skipped["works with a competitor"] += 1
            continue
        if (m.get("brand_safety") if m.get("brand_safety") is not None else 100) < 50:  # 0 is a real score
            skipped["brand-safety risk"] += 1
            continue
        if new_only and is_partner and is_partner(c, m):
            skipped["worked with you before"] += 1
            continue
        price, views = c.get("price"), c.get("median_views") or c.get("avg_views")
        if not price or not views:
            skipped["no price estimate (e.g. Twitch)" if c["platform"] == "twitch" else "no views or price data"] += 1
            continue
        if (m.get("fit") or 0) < min_fit:
            skipped[f"Fit under {min_fit}"] += 1
            continue
        if need_email and not c.get("emails"):
            skipped["no email"] += 1
            continue
        cost = (price["low"] + price["high"]) / 2
        worth = _worth(c, m, goal)
        candidates.append({"c": c, "m": m, "cost": cost, "worth": worth, "views": views})
    candidates.sort(key=lambda x: -x["worth"] / x["cost"])

    picked, spent, people = [], 0.0, set()
    for x in candidates:
        if len(picked) >= max_creators:
            break
        # One post per person: profiles that link to each other, or the same name on two platforms ("Kakkuh").
        keys = {min(groups.get(x["c"]["id"], [x["c"]["id"]]))}
        name = re.sub(r"[^a-z0-9]", "", (x["c"].get("name") or "").lower())
        if len(name) >= 4:
            keys.add("name:" + name)
        if keys & people or spent + x["cost"] > budget:
            continue
        picked.append(x)
        spent += x["cost"]
        people |= keys

    def item(x):
        c, m = x["c"], x["m"]
        country = m.get("country") or c.get("country") or ""
        return {
            "id": c["id"], "name": c.get("name"), "platform": c["platform"], "handle": c.get("handle"),
            "country": country, "market": MARKETS.get(country, {}).get("name", country),
            "followers": c.get("followers"), "tier": c.get("tier"), "views": x["views"], "price": c["price"],
            "fit": m.get("fit"), "quality": m.get("quality"), "score": m.get("score"),
            "hidden_gem": bool(m.get("hidden_gem")), "partner": bool(is_partner and is_partner(c, m)),
            "email": (c.get("emails") or [None])[0], "summary": m.get("summary") or "",
            "cost_per_1k_views": round(1000 * x["cost"] / x["views"], 2) if x["views"] else None,
        }

    items = [item(x) for x in picked]
    low = sum(x["c"]["price"]["low"] for x in picked)
    high = sum(x["c"]["price"]["high"] for x in picked)
    views = sum(x["views"] for x in picked)
    # The alternative a marketer would weigh it against: the single biggest creator the same budget buys.
    single = max((x for x in candidates if x["cost"] <= budget), key=lambda x: x["views"], default=None)
    return {
        "budget": budget,
        "goal": goal,
        "count": len(items),
        "items": items,
        "cost": {"low": low, "high": high, "mid": round(spent)},
        "views": views,
        "cost_per_1k_views": round(1000 * spent / views, 2) if views else None,
        "markets": dict(Counter(i["market"] or "Unknown" for i in items).most_common()),
        "platforms": dict(Counter(PLATFORMS.get(i["platform"], i["platform"]) for i in items).most_common()),
        "sizes": dict(Counter(TIER_NAMES.get(i["tier"], "unknown") for i in items).most_common()),
        "hidden_gems": sum(1 for i in items if i["hidden_gem"]),
        "with_email": sum(1 for i in items if i["email"]),
        "candidates": len(candidates),
        "left_out": dict(skipped),
        "single_best": ({"name": single["c"].get("name"), "views": single["views"], "cost": round(single["cost"]),
                         "platform": single["c"]["platform"]} if single and single["c"]["id"] not in {i["id"] for i in items} else None),
        "note": "One sponsored post each, at their typical views. Prices are estimates from common rates: negotiate from here.",
    }
