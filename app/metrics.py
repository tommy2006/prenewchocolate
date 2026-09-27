"""Deterministic creator metrics: windowed average views, engagement vs. size-typical benchmarks,
views trend, activity, and contact extraction."""
import math
import re
from datetime import datetime, timezone

from .markets import tier_of

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
# Addresses in descriptions that are clearly not the creator's own
JUNK_EMAIL = re.compile(r"noreply|no-reply|example\.|@sentry|@wix|\.(png|jpe?g|gif|webp)$")

SOCIAL_PATTERNS = {
    "youtube": re.compile(r"https?://(?:www\.)?youtube\.com/(?:@|c/|channel/)[\w.\-]+", re.I),
    "tiktok": re.compile(r"https?://(?:www\.)?tiktok\.com/@[\w.\-]+", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[\w.]+/?", re.I),
    "twitch": re.compile(r"https?://(?:www\.)?twitch\.tv/[\w]+", re.I),
    "x": re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/[\w]+", re.I),
    "discord": re.compile(r"https?://(?:www\.)?discord\.(?:gg|com/invite)/[\w\-]+", re.I),
    "kick": re.compile(r"https?://(?:www\.)?kick\.com/[\w\-]+", re.I),
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[\w.\-]+", re.I),
}

# What "normal" engagement looks like for an account of this size, per platform.
# YouTube/TikTok: interactions per view. Instagram: interactions per follower.
TYPICAL_RATE = {
    "youtube": {"nano": 0.045, "micro": 0.04, "mid": 0.035, "macro": 0.03},
    "tiktok": {"nano": 0.08, "micro": 0.07, "mid": 0.06, "macro": 0.05},
    "instagram": {"nano": 0.045, "micro": 0.025, "mid": 0.015, "macro": 0.01},
}
# Average views per follower (how much of the audience actually shows up).
TYPICAL_REACH = {
    "youtube": {"nano": 0.3, "micro": 0.2, "mid": 0.12, "macro": 0.08},
    "tiktok": {"nano": 0.6, "micro": 0.4, "mid": 0.25, "macro": 0.15},
}

MIN_AGE_DAYS = 2  # views on brand-new posts are still climbing, so they'd drag the average down


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _avg(values):
    values = [v for v in values if isinstance(v, (int, float)) and v >= 0]
    return sum(values) / len(values) if values else None


def _median(values):
    values = sorted(v for v in values if isinstance(v, (int, float)) and v >= 0)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def _vs_typical_score(ratio: float) -> float:
    """1x typical -> 50, 2x -> 75, 4x -> 100, 0.5x -> 25."""
    if ratio <= 0:
        return 0.0
    return max(0.0, min(100.0, 50 + 25 * math.log2(ratio)))


def extract_emails(*texts) -> list[str]:
    found = []
    for text in texts:
        for email in EMAIL_RE.findall(text or ""):
            email = email.strip(".").lower()
            if email not in found and not JUNK_EMAIL.search(email):
                found.append(email)
    return found[:3]


def extract_links(*texts) -> list[str]:
    found = []
    for text in texts:
        for url in URL_RE.findall(text or ""):
            url = url.rstrip(".,;")
            if url not in found:
                found.append(url)
    return found[:8]


MENTION = re.compile(r"(?<![\w.@/])@([A-Za-z0-9_.\-]{3,30})")


def mentions_in(own_handle: str, *texts) -> list[str]:
    """@handles written in posts ("ft. @friend"), lowercased, their own left out. Emails aren't matched."""
    own = own_handle.lstrip("@").lower()
    found = [h.lower().rstrip(".-") for text in texts for h in MENTION.findall(text or "")]
    return [h for h in dict.fromkeys(found) if h != own and len(h) >= 3][:15]


def extract_socials(own_platform: str, *texts) -> dict[str, str]:
    """The creator's other profiles (first match per network), e.g. their Instagram linked from a YouTube bio."""
    found = {}
    for text in texts:
        for network, pattern in SOCIAL_PATTERNS.items():
            if network != own_platform and network not in found:
                m = pattern.search(text or "")
                if m:
                    found[network] = m.group(0).rstrip("/.,;")
    return found


def _views_window(posts: list[dict], now: datetime) -> tuple[list[dict], str]:
    """Posts to average views over: the last 30 days for active creators, else 90 days, else the latest posts."""
    dated = [(d, p) for p in posts if (d := _parse_date(p.get("date"))) and p.get("views") is not None]
    settled = [(d, p) for d, p in dated if (now - d).days >= MIN_AGE_DAYS] or dated
    for days, minimum in ((30, 3), (90, 2)):
        window = [p for d, p in settled if (now - d).days <= days]
        if len(window) >= minimum:
            return window, f"{days} days"
    latest = [p for _, p in sorted(settled, key=lambda x: x[0], reverse=True)[:10]]
    return latest, (f"last {len(latest)} posts" if latest else "")


def _trend(posts: list[dict], now: datetime) -> float | None:
    """Average views of the last 30 days vs the 60 days before. None if either side has under 2 posts."""
    recent, older = [], []
    for p in posts:
        d = _parse_date(p.get("date"))
        if not d or p.get("views") is None or (now - d).days < MIN_AGE_DAYS:
            continue
        age = (now - d).days
        (recent if age <= 30 else older if age <= 90 else []).append(p["views"])
    if len(recent) < 2 or len(older) < 2 or not _avg(older):
        return None
    return round(_avg(recent) / _avg(older) - 1, 2)


def trend_label(trend: float | None) -> str:
    if trend is None:
        return ""
    return "Growing" if trend >= 0.2 else "Declining" if trend <= -0.2 else "Stable"


def compute(creator: dict) -> dict:
    """Fill in derived metrics on a normalized creator dict (mutates and returns it)."""
    compute_stats(creator)
    # Contacts: bio first (most likely the creator's own), then video descriptions ("Business: ...").
    extra = creator.pop("_contact_text", "")
    bio_texts = [creator.get("bio", ""), creator.get("bio_link") or ""]
    creator["emails"] = extract_emails(creator.get("public_email") or "", *bio_texts, extra)
    links = extract_links(*bio_texts)
    if creator.get("bio_link") and str(creator["bio_link"]).startswith("http") and creator["bio_link"] not in links:
        links.insert(0, creator["bio_link"])
    creator["links"] = links
    creator["socials"] = extract_socials(creator["platform"], *bio_texts, extra)
    return creator


def compute_stats(creator: dict) -> dict:
    """Views, engagement, trend and activity from the stored posts. Safe to run again on saved creators."""
    platform = creator["platform"]
    followers = creator.get("followers")
    now = datetime.now(timezone.utc)
    all_posts = [p for p in creator.get("recent_posts", []) if not p.get("pinned")] or creator.get("recent_posts", [])
    tier = tier_of(followers)
    creator["tier"] = tier

    # YouTube: average normal videos (where sponsored integrations run) unless the channel is mostly Shorts.
    basis_posts, basis = all_posts, "all posts"
    if platform == "youtube":
        long_form = [p for p in all_posts if not p.get("is_short")]
        shorts = len(all_posts) - len(long_form)
        creator["shorts_share"] = round(shorts / len(all_posts), 2) if all_posts else None
        if len(_views_window(long_form, now)[0]) >= 2:
            basis_posts, basis = long_form, "videos, Shorts excluded"
        elif shorts:
            basis = "incl. Shorts"
    window, window_label = _views_window(basis_posts, now)
    creator["views_window"] = window_label
    creator["views_basis"] = basis
    creator["posts_in_window"] = len(window)

    avg_views = _avg([p.get("views") for p in window])
    median_views = _median([p.get("views") for p in window])
    avg_likes = _avg([p.get("likes") for p in window])
    avg_comments = _avg([p.get("comments") for p in window])
    if avg_views is None:  # e.g. Instagram photos have no views: fall back to all recent posts for likes
        avg_likes = _avg([p.get("likes") for p in all_posts])
        avg_comments = _avg([p.get("comments") for p in all_posts])
    creator["avg_views"] = round(avg_views) if avg_views is not None else None
    creator["avg_likes"] = round(avg_likes) if avg_likes is not None else None
    creator["avg_comments"] = round(avg_comments) if avg_comments is not None else None
    creator["median_views"] = round(median_views) if median_views is not None else None
    # Consistency: share of posts reaching at least half the average. One viral hit among flops scores low.
    viewed = sorted(p["views"] for p in window if isinstance(p.get("views"), (int, float)))
    if len(viewed) >= 4 and avg_views:
        creator["consistency"] = round(sum(1 for v in viewed if v >= avg_views / 2) / len(viewed), 2)
        creator["views_spread"] = round(avg_views / median_views, 2) if median_views else None
        # The middle half of their posts: what a sponsored post can expect, without the one viral hit or flop.
        n = len(viewed)
        creator["views_range"] = [round(viewed[n // 4]), round(viewed[max(n // 4, (3 * n) // 4 - 1)])]
    else:
        creator["consistency"] = creator["views_spread"] = creator["views_range"] = None

    creator["views_trend"] = _trend(basis_posts, now)
    creator["trend"] = trend_label(creator["views_trend"])

    rate = reach = None
    # Likes per view from posts where both are known (our TikTok scraper reads likes on a few videos only).
    paired = [p for p in window if p.get("views") and isinstance(p.get("likes"), (int, float))]
    if platform in ("youtube", "tiktok") and paired:
        rate = sum(p["likes"] + (p.get("comments") or 0) for p in paired) / sum(p["views"] for p in paired)
    elif platform == "instagram" and followers:
        rate = ((avg_likes or 0) + (avg_comments or 0)) / followers
    # Median, not mean: a single viral video shouldn't make the whole audience look engaged.
    typical_views = median_views if median_views is not None else avg_views
    if platform in TYPICAL_REACH and typical_views is not None and followers:
        reach = typical_views / followers
    creator["engagement_rate"] = round(rate, 4) if rate is not None else None
    creator["reach"] = round(reach, 3) if reach is not None else None

    ratios = []
    if rate is not None and tier:
        ratios.append(rate / TYPICAL_RATE[platform][tier])
    if reach is not None and tier:
        ratios.append(reach / TYPICAL_REACH[platform][tier])
    if ratios:
        vs = math.prod(ratios) ** (1 / len(ratios))  # geometric mean
        creator["engagement_vs_typical"] = round(vs, 2)
        creator["engagement_score"] = round(_vs_typical_score(vs))
    else:
        creator["engagement_vs_typical"] = None
        creator["engagement_score"] = 40  # unknown: slightly below typical

    dates = sorted((d for d in (_parse_date(p.get("date")) for p in all_posts) if d), reverse=True)
    if dates:
        days_since = max(0, (now - dates[0]).days)
        span_days = max(7, (dates[0] - dates[-1]).days) if len(dates) > 1 else 30
        per_month = min(60.0, (len(dates) - 1 if len(dates) > 1 else 1) / span_days * 30)
        creator["last_post_at"] = dates[0].isoformat(timespec="seconds")
        creator["days_since_last_post"] = days_since
        creator["posts_per_month"] = round(per_month, 1)
        if days_since <= 7:
            recency = 100
        elif days_since <= 30:
            recency = 100 - (days_since - 7) * 40 / 23
        elif days_since <= 90:
            recency = 60 - (days_since - 30) * 40 / 60
        else:
            recency = max(0, 20 - (days_since - 90) * 20 / 90)
        frequency = min(100, per_month / 8 * 100)
        creator["activity_score"] = round(0.6 * recency + 0.4 * frequency)
    else:
        creator["last_post_at"] = None
        creator["days_since_last_post"] = None
        creator["posts_per_month"] = None
        creator["activity_score"] = 30
    return creator


def content_format(creator: dict) -> str:
    """What they mostly make: "long" videos, "short" ones (Shorts, TikTok, Reels) or "live" streams."""
    platform = creator["platform"]
    if platform == "twitch":
        return "live"
    if platform in ("tiktok", "instagram"):
        return "short"
    share = creator.get("shorts_share")
    return "short" if share is not None and share >= 0.6 else "long"


def prescore(creator: dict) -> float:
    """Cheap ranking used to decide who is worth sending to the AI."""
    return 0.6 * creator.get("engagement_score", 40) + 0.4 * creator.get("activity_score", 30)


def in_range(followers, fmin, fmax) -> bool:
    if followers is None:
        return False
    return followers >= (fmin or 0) and (fmax is None or followers <= fmax)


FREE_MAIL = re.compile(
    r"@(gmail|googlemail|outlook|hotmail|live|msn|yahoo|ymail|icloud|me|mac|aol|proton|protonmail|pm|gmx|web|"
    r"t-online|freenet|mail|email|yandex|seznam|wp|o2|onet|interia|zoho|inbox|luukku|kolumbus|telia|"
    r"freemail|citromail)\.", re.I)
AGENCY_WORDS = re.compile(
    r"\b(management|mgmt|agency|agentur|talent|represented by|managed by|booking|vertretung|byrå|toimisto|"
    r"agentūra|aģentūra|ügynökség|agencja)\b|mgmt|talents?\.", re.I)


def agency_hint(creator: dict) -> bool:
    """Best guess whether collaborations go through an agency or management rather than the creator.

    True when the bio mentions management/an agency, or a business email sits on a company domain
    that isn't the creator's own (e.g. gamer@some-agency.gg, not hello@gamername.com)."""
    emails = creator.get("emails") or []
    if AGENCY_WORDS.search(creator.get("bio") or "") or any(AGENCY_WORDS.search(e) for e in emails):
        return True
    own = {re.sub(r"[^a-z0-9]", "", s.lower()) for s in (creator.get("name") or "", creator.get("handle") or "")}
    own = {o for o in own if len(o) >= 4}
    for email in emails:
        if FREE_MAIL.search(email):
            continue
        domain = re.sub(r"[^a-z0-9]", "", email.split("@")[1].rsplit(".", 1)[0].lower())
        if not any(o in domain or domain in o for o in own):
            return True
    return False
