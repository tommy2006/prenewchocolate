"""The match model, in one place.

Two headline numbers instead of one opaque score:
- **Fit** (would a marketer pick them for this brand?): content, audience, market, brand, readiness
- **Quality** (is the audience real and paying attention?): authenticity, engagement, consistency, activity, momentum

The overall **match** used for ranking blends the two; the brand's campaign goal decides how.
Every sub-score comes with evidence (claims that cite posts or comments) and a confidence level.
"""

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


def quality_parts(c: dict) -> dict:
    auth = (c.get("authenticity") or {}).get("score")
    consistency = c.get("consistency")
    trend = c.get("views_trend")
    return {
        "authenticity": clamp(auth, 60) if auth is not None else 60,
        "engagement": clamp(c.get("engagement_score"), 40),
        "consistency": clamp(consistency * 100) if consistency is not None else 50,
        "activity": clamp(c.get("activity_score"), 30),
        "momentum": clamp(50 + trend * 100) if trend is not None else 50,
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
    else:
        notes.append(f"Likes known for only {with_likes} posts" + (" (TikTok shows them per video)" if c["platform"] == "tiktok" else ""))
    if ((c.get("audience") or {}).get("sampled") or 0) >= 20:
        points += 1
    else:
        notes.append("Comments not sampled" + (" (not available for TikTok)" if c["platform"] == "tiktok" else ""))
    if c.get("country"):
        points += 1
    level = "high" if points >= 5 else "medium" if points >= 3 else "low"
    return {"level": level, "notes": notes}


def evidence_item(dim: str, sign: str, text: str, posts: list[dict] | None = None, quotes: list[str] | None = None,
                  src: str = "data", fact: bool = True) -> dict:
    """One claim behind a score. `posts` are {"title", "url"}; `quotes` are comment snippets."""
    return {"dim": dim, "sign": sign, "text": text, "posts": posts or [], "quotes": quotes or [], "src": src, "fact": fact}


def cite(posts: list[dict], limit: int = 3) -> list[dict]:
    return [{"title": (p.get("title") or "")[:100], "url": p.get("url")} for p in posts[:limit] if p.get("url")]
