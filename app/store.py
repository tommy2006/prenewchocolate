"""A small JSON-file database. Plenty for a demo-sized dataset (a few thousand creators)."""
import copy
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from .config import DB_PATH


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


PRENEW = {
    "id": "co_prenew",
    "name": "Prenew",
    "description": (
        "Finnish startup building Europe's most trusted marketplace for refurbished gaming PCs. "
        "Founded 2024, operating across Europe from Espoo and Berlin. Sells tested, warrantied "
        "second-hand gaming PCs at a lower price and footprint than buying new."
    ),
    # Creator types shown as one-click chips in the search area. Built from Prenew's collaboration history:
    # mostly gaming creators (Minecraft, Fortnite, GTA, ARK...) plus gaming-tech and gear channels.
    "suggested_tags": ["Minecraft", "Fortnite", "GTA", "Gaming news", "Gaming tech", "Gaming gear",
                       "Gaming comedy", "Budget gaming", "PC building", "FPS gaming"],
    "search": None,  # filled from DEFAULT_SEARCH below
    # One-click searches for people who don't know what to type (new companies get AI-written ones).
    "suggested_searches": [
        {"title": "Minecraft & Fortnite creators, Finland",
         "description": "Prenew's most common partner: Finnish gaming channels whose young viewers want their first gaming PC.",
         "query": "", "tags": ["Minecraft", "Fortnite"], "markets": ["FI"], "platforms": ["youtube", "tiktok"],
         "follower_min": 5000, "follower_max": 500000},
        {"title": "Swedish gaming & tech TikTok",
         "description": "Short gaming-news and tech videos, the style of most of Prenew's Swedish collaborations.",
         "query": "", "tags": ["Gaming news", "Gaming tech"], "markets": ["SE"], "platforms": ["tiktok"],
         "follower_min": 4000, "follower_max": 250000},
        {"title": "Baltic gaming creators",
         "description": "Estonia, Latvia and Lithuania: small markets where a few thousand followers already reach many local gamers.",
         "query": "", "tags": ["Minecraft", "GTA"], "markets": ["EE", "LV", "LT"], "platforms": ["tiktok", "youtube"],
         "follower_min": 2000, "follower_max": 100000},
        {"title": "German game-specific TikTokers",
         "description": "Creators focused on one game (ARK, GTA, Souls-likes) or on gaming gear, 5k to 300k followers.",
         "query": "", "tags": ["Gaming gear", "GTA"], "markets": ["DE"], "platforms": ["tiktok"],
         "follower_min": 5000, "follower_max": 300000},
        {"title": "Polish & Hungarian gaming YouTube",
         "description": "Newer markets for Prenew, where bigger gaming YouTube channels give the fastest reach.",
         "query": "", "tags": ["Minecraft", "Gaming comedy"], "markets": ["PL", "HU"], "platforms": ["youtube"],
         "follower_min": 50000, "follower_max": 500000},
        {"title": "Hidden gems: tiny but loyal",
         "description": "Nordic and Baltic gaming creators under 10k followers with unusually engaged audiences; cheap and trusted.",
         "query": "", "tags": ["Minecraft", "Fortnite"], "markets": ["FI", "SE", "EE"], "platforms": ["tiktok", "youtube"],
         "follower_min": 500, "follower_max": 10000},
    ],
    "seed_version": 2,
}

# Prenew's first curated searches (before we had their collaboration history); replaced on upgrade.
_OLD_PRENEW_TITLES = {"Budget PC builders in Finland", "German tech reviewers, 50k-250k", "CS2 & Valorant on TikTok",
                      "Gaming setup & streaming creators", "Second-hand & sustainable tech", "Hidden gems: tiny but loyal"}
_OLD_PRENEW_TAGS = {"PC building", "Budget gaming", "Hardware reviews", "Gaming setup", "Esports",
                    "Streaming setup", "Sustainable tech", "FPS gaming"}

# What the user picks in the search area. Saved per company so it's there next time.
DEFAULT_SEARCH = {
    "tags": [],
    "markets": [],
    "platforms": [],
    "tiers": [],
    "follower_min": None,  # size slider; None = no lower/upper limit
    "follower_max": None,
    "deal_types": [],
    "avoid": [],
    "example_creators": [],
    "ai_scout": False,
}
PRENEW["search"] = {
    **DEFAULT_SEARCH,
    "markets": ["FI", "SE", "DE"],
    "deal_types": ["Gifted product", "Affiliate / discount code"],
    "avoid": ["Gambling or skin betting", "Sponsored by competing PC retailers"],
}

# Fields that used to live on the company profile before they moved into the search area.
_OLD_PROFILE_FIELDS = ("website", "creator_brief", "tags", "markets", "platforms", "follower_min",
                       "follower_max", "deal_types", "avoid", "example_creators")


def _migrate_company(co: dict) -> None:
    if co.get("search") is None:
        co["search"] = {
            **DEFAULT_SEARCH,
            **{k: co[k] for k in ("markets", "deal_types", "avoid", "example_creators") if co.get(k)},
        }
    co.setdefault("suggested_tags", co.get("tags") or [])
    co.setdefault("suggested_searches", copy.deepcopy(PRENEW["suggested_searches"]) if co.get("id") == PRENEW["id"] else [])
    for key in ("follower_min", "follower_max"):
        co["search"].setdefault(key, None)
    if co.get("scout_off") is None:
        # The web scout runs paid Claude web searches; it's opt-in per search now, never left on by default.
        co["search"]["ai_scout"] = False
        co["scout_off"] = True
    if co.get("id") == PRENEW["id"] and co.get("seed_version", 1) < PRENEW["seed_version"]:
        # Searches and creator types based on Prenew's real collaborations; keep anything the user added.
        own = [x for x in co.get("suggested_searches", []) if x.get("title") not in _OLD_PRENEW_TITLES]
        co["suggested_searches"] = copy.deepcopy(PRENEW["suggested_searches"]) + own
        own_tags = [t for t in co.get("suggested_tags", []) if t not in _OLD_PRENEW_TAGS]
        co["suggested_tags"] = list(dict.fromkeys(PRENEW["suggested_tags"] + own_tags))
        co["seed_version"] = PRENEW["seed_version"]
    for key in _OLD_PROFILE_FIELDS:
        co.pop(key, None)


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.companies: dict[str, dict] = {}
        self.creators: dict[str, dict] = {}
        self.matches: dict[str, dict[str, dict]] = {}  # company_id -> creator_id -> match
        self.jobs: dict[str, dict] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.companies = data.get("companies", {})
            self.creators = data.get("creators", {})
            self.matches = data.get("matches", {})
            self.jobs = data.get("jobs", {})
        for job in self.jobs.values():
            if job.get("status") in ("queued", "running"):
                job["status"] = "error"
                job["error"] = "Interrupted by a server restart"
        for company in self.companies.values():
            _migrate_company(company)
        if not self.companies:
            self.companies[PRENEW["id"]] = {**copy.deepcopy(PRENEW), "created_at": now_iso()}
        self.save()

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            payload = {
                "companies": self.companies,
                "creators": self.creators,
                "matches": self.matches,
                "jobs": self.jobs,
            }
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)


store = Store(DB_PATH)
