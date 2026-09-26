"""The match model, in one place.

Two headline numbers instead of one opaque score:
- **Fit** (would a marketer pick them for this brand?): content, audience, market, brand, readiness
- **Quality** (is the audience real and paying attention?): authenticity, engagement, consistency, activity, momentum

The overall **match** used for ranking blends the two; the brand's campaign goal decides how.
Every sub-score comes with evidence (claims that cite posts or comments) and a confidence level.
"""
import math


FIT_PARTS = {
    "content": "Content",
    "audience": "Audience",
    "market": "Market",
    "brand": "Brand & safety",
    "readiness": "Readiness & cost",
}
QUALITY_PARTS = {
    "authenticity": ("Authenticity", 0.35),
    "engagement": ("Engagement", 0.30),
    "consistency": ("Consistency", 0.15),
    "activity": ("Activity", 0.10),
    "momentum": ("Momentum", 0.10),
}
# Campaign goal -> share of Fit in the overall match, and how Fit's parts are weighed.
GOALS = {
    "sales": {"fit": 0.65, "parts": {"content": 0.30, "audience": 0.30, "market": 0.20, "brand": 0.10, "readiness": 0.10}},
    "balanced": {"fit": 0.60, "parts": {"content": 0.35, "audience": 0.25, "market": 0.20, "brand": 0.10, "readiness": 0.10}},
    "awareness": {"fit": 0.50, "parts": {"content": 0.35, "audience": 0.15, "market": 0.25, "brand": 0.10, "readiness": 0.15}},
}


VERSION = 4  # bump when scores are computed differently, so saved matches are re-scored on start
UNPROVEN_MAX = 70  # a fit part with nothing cited behind it can't count as strong


def clamp(value, default: int = 0) -> int:
    """0-100 int; tolerates "85" or 85.0 from less strict models, and uses `default` for anything unreadable."""
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def goal_of(company: dict) -> str:
    goal = ((company or {}).get("profile") or {}).get("goal") or "balanced"
    return goal if goal in GOALS else "balanced"


def fit(parts: dict, goal: str, competitor: bool, safety: int) -> int:
    weights = GOALS[goal]["parts"]
    score = sum(weights[k] * parts[k] for k in weights)
    if competitor:
        score -= 20
    if safety < 50:
        score -= 20
    if parts["content"] < 30:  # unrelated content (news, music, lifestyle) shouldn't ride on a good audience
        score = min(score, 35)
    return clamp(score)


def consistency_score(c: dict) -> int:
    """From the middle half of their posts: 2k-2.5k views is steady (90+), 1k-7k swings a lot (under 20)."""
    rng = c.get("views_range")
    if not rng or not rng[0]:
        return 50
    return clamp(100 - 30 * math.log2(max(1.0, rng[1] / rng[0])))


def momentum_score(trend: float | None) -> int:
    """Views trend -> 0-100 on a curve: +30% is good (~70), only a doubling gets past 90."""
    if trend is None:
        return 50
    return clamp(50 + 45 * math.tanh(trend / 0.6))


def quality_parts(c: dict) -> dict:
    auth = (c.get("authenticity") or {}).get("score")
    return {
        "authenticity": clamp(auth, 60) if auth is not None else 60,
        "engagement": clamp(c.get("engagement_score"), 40),
        "consistency": consistency_score(c),
        "activity": clamp(c.get("activity_score"), 30),
        "momentum": momentum_score(c.get("views_trend")),
    }


def quality(parts: dict) -> int:
    return clamp(sum(w * parts[k] for k, (_, w) in QUALITY_PARTS.items()))


def overall(fit_score: int, quality_score: int, goal: str, authenticity: int) -> int:
    w = GOALS[goal]["fit"]
    score = w * fit_score + (1 - w) * quality_score
    if authenticity < 40:
        score -= 10
    return clamp(score)


def confidence(c: dict, checked: str) -> dict:
    """How much the scores rest on: an AI reading the posts, enough posts, likes, comments, a known country."""
    notes, points = [], 0
    if checked == "deep":
        points += 2
    elif checked == "ai":
        points += 1
    else:
        notes.append("Quick score: the AI hasn't read their posts yet")
    if (c.get("posts_in_window") or 0) >= 4:
        points += 1
    else:
        notes.append("Few recent posts to judge from")
    with_likes = sum(1 for p in c.get("recent_posts", []) if isinstance(p.get("likes"), (int, float)))
    if with_likes >= 5:
        points += 1
    elif c["platform"] == "twitch":
        notes.append("Twitch shows no likes or comments, and no live viewer history")
    else:
        notes.append(f"Likes known for only {with_likes} posts" + (" (TikTok shows them per video)" if c["platform"] == "tiktok" else ""))
    if ((c.get("audience") or {}).get("sampled") or 0) >= 20:
        points += 1
    elif c["platform"] != "twitch":
        notes.append("Comments not sampled" + (" (not available for TikTok)" if c["platform"] == "tiktok" else ""))
    if c.get("country"):
        points += 1
    level = "high" if points >= 5 else "medium" if points >= 3 else "low"
    return {"level": level, "notes": notes}


def evidence_item(dim: str, sign: str, text: str, posts: list[dict] | None = None, quotes: list[str] | None = None,
                  src: str = "data", fact: bool = True) -> dict:
    """One claim behind a score. `posts` are {"title", "url"}; `quotes` are comment snippets."""
    return {"dim": dim, "sign": sign, "text": text, "posts": posts or [], "quotes": quotes or [], "src": src, "fact": fact}


NEUTRAL_BASIS = {
    "content": "Nothing in their recent posts shows this either way yet",
    "audience": "Nothing yet shows who watches (age, interests, buying intent): a neutral starting value",
    "market": "Where they and their viewers are isn't clear yet: a neutral starting value",
    "brand": "Nothing in their recent posts shows this either way yet",
    "readiness": "Nothing yet shows how ready they are for a collaboration: a neutral starting value",
}


def hold_back_unproven(parts: dict, evidence: list[dict], ai: bool, raw: dict | None = None) -> tuple[dict, list, dict]:
    """Every fit part should say where its number comes from. A part with no claim behind it gets a "?" line
    saying so, and an AI score above UNPROVEN_MAX with nothing cited counts as UNPROVEN_MAX until there's
    evidence. Returns (parts, extra evidence, {part: the AI's own number} for the ones held back).
    `raw`: numbers held back earlier (re-scoring keeps the AI's original judgement)."""
    have = {e["dim"] for e in evidence if e.get("sign") in ("+", "-")}
    parts, notes, held = dict(parts), [], {}
    for dim in FIT_PARTS:
        if dim in have:
            continue
        value = (raw or {}).get(dim, parts[dim])
        if ai and value > UNPROVEN_MAX:
            parts[dim], held[dim] = UNPROVEN_MAX, value
            text = f"The AI rated this {value} but cited no post or comment: counted as {UNPROVEN_MAX} until there's evidence"
        elif ai:
            text = "The AI's overall judgement: it cited no post or comment for this"
        else:
            text = NEUTRAL_BASIS[dim]
        notes.append(evidence_item(dim, "?", text, src="basis", fact=False))
    return parts, notes, held


def cite(posts: list[dict], limit: int = 3) -> list[dict]:
    return [{"title": (p.get("title") or "")[:100], "url": p.get("url")} for p in posts[:limit] if p.get("url")]


# --- Short explanations (hover texts), about this creator -------------------------------------------

def _short(n) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e4 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(round(n))


def _clip(text: str, n: int = 80) -> str:
    text = (text or "").strip().rstrip(".")
    return text if len(text) <= n else text[: n - 1].rsplit(" ", 1)[0] + "…"


def quality_notes(c: dict) -> dict:
    """One short line per audience-quality part, with a sign: "+" good, "-" a concern, "" neutral."""
    notes = {}
    auth = c.get("authenticity") or {}
    warn = [s for s in auth.get("signals", []) if s["kind"] != "good"]
    good = [s for s in auth.get("signals", []) if s["kind"] == "good"]
    if warn:
        notes["authenticity"] = ("-", warn[0]["text"])
    elif good:
        notes["authenticity"] = ("+", good[0]["text"])
    elif auth.get("confidence") == "low":
        notes["authenticity"] = ("", "No warning signs, but too little data to confirm the audience is real")
    else:
        notes["authenticity"] = ("", "No warning signs found")
    vs = c.get("engagement_vs_typical")
    if vs is not None:
        notes["engagement"] = ("+" if vs >= 1.2 else "-" if vs < 0.8 else "",
                               f"{vs}× the engagement typical for their size")
    else:
        notes["engagement"] = ("", "Engagement unknown: no likes data")
    rng = c.get("views_range")
    if rng and rng[0]:
        ratio = rng[1] / rng[0]
        text = f"Most posts get {_short(rng[0])}–{_short(rng[1])} views"
        if (c.get("views_spread") or 0) >= 2:
            text += "; the average is lifted by a viral hit"
        notes["consistency"] = ("+" if ratio <= 2 else "-" if ratio >= 3 else "", text if ratio <= 3 else "Views swing a lot: " + text[0].lower() + text[1:])
    else:
        notes["consistency"] = ("", "Too few recent posts to judge")
    ppm, days = c.get("posts_per_month"), c.get("days_since_last_post")
    if ppm is not None and days is not None:
        sign = "+" if ppm >= 4 and days <= 14 else "-" if days > 30 or ppm < 2 else ""
        notes["activity"] = (sign, f"Posts {ppm:g} times a month, last post {'today' if days == 0 else f'{days} days ago'}")
    else:
        notes["activity"] = ("", "Posting rhythm unknown")
    t = c.get("views_trend")
    if t is None:
        notes["momentum"] = ("", "Not enough posts to see a trend")
    elif abs(t) < 0.1:
        notes["momentum"] = ("", "Views steady over the last 3 months")
    else:
        notes["momentum"] = ("+" if t >= 0.2 else "-" if t <= -0.2 else "",
                             f"Views {'up' if t > 0 else 'down'} {abs(round(t * 100))}% in the last 30 days")
    return notes


def _sorted_pros(evidence: list[dict]) -> list[dict]:
    order = ["content", "audience", "market", "readiness", "brand"]
    return sorted((e for e in evidence if e["sign"] == "+"),
                  key=lambda e: (e.get("src") != "ai", order.index(e["dim"]) if e["dim"] in order else 9))


def fit_word(s: int) -> str:
    return "Excellent fit" if s >= 85 else "Strong fit" if s >= 75 else "Possible fit" if s >= 55 else "Weak fit"


def quality_word(s: int) -> str:
    return "Excellent audience" if s >= 85 else "Healthy audience" if s >= 75 else "Mixed audience" if s >= 55 else "Doubtful audience"


def explain(c: dict, m: dict) -> dict:
    """Hover texts: first line = the verdict, then up to three short reasons about *this* creator.
    Lines start with "+ " (helps), "- " (hurts) or "? " (not checked)."""
    ev = m.get("evidence") or []
    pros, cons = _sorted_pros(ev), [e for e in ev if e["sign"] == "-"]
    fit_lines = [f"+ {_clip(e['text'], 70)}" for e in pros[:2]] + [f"- {_clip(e['text'], 70)}" for e in cons[:1]]
    if m.get("checked", "rules") == "rules":
        fit_lines.append("? Quick estimate: the AI hasn't read their posts yet")
    notes = quality_notes(c)
    ranked = sorted(notes.items(), key=lambda kv: {"-": 0, "+": 1, "": 2}[kv[1][0]])
    q_lines = [f"{sign or '?'} {_clip(text, 70)}" for _, (sign, text) in ranked if sign][:3] or \
              [f"? {_clip(notes['authenticity'][1], 70)}"]
    parts = {}
    for dim in FIT_PARTS:
        claims = [e for e in ev if e["dim"] == dim]
        claims.sort(key=lambda e: e["sign"] != "-")  # a concern first: it explains why it isn't 100
        parts[dim] = "\n".join({"-": "- ", "?": "? "}.get(e["sign"], "+ ") + _clip(e["text"], 70) for e in claims[:2]) \
            or "? No specific evidence either way"
    return {
        "fit": "\n".join([f"{fit_word(m.get('fit', 0))} · {m.get('fit', 0)}"] + fit_lines),
        "quality": "\n".join([f"{quality_word(m.get('quality') or 0)} · {m.get('quality')}"] + q_lines),
        "parts": parts,
        "qparts": {k: f"{sign or '?'} {_clip(text, 90)}" for k, (sign, text) in notes.items()},
    }
