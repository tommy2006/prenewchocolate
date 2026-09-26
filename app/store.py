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
    # Creator types Claude suggested from the description; shown as one-click chips in the search area.
    "suggested_tags": ["PC building", "Budget gaming", "Hardware reviews", "Gaming setup", "Esports",
                       "Streaming setup", "Sustainable tech", "FPS gaming"],
    "search": None,  # filled from DEFAULT_SEARCH below
    # One-click searches for people who don't know what to type (new companies get AI-written ones).
    "suggested_searches": [
        {"title": "Budget PC builders in Finland",
         "description": "Finnish YouTubers who build or upgrade affordable gaming PCs: their viewers are shopping for exactly this.",
         "query": "", "tags": ["PC building", "Budget gaming"], "markets": ["FI"], "platforms": ["youtube"],
         "follower_min": 1000, "follower_max": None},
        {"title": "German tech reviewers, 50k-250k",
         "description": "Mid-size German hardware reviewers, the subscriber range where Prenew already runs most collaborations.",
         "query": "", "tags": ["Hardware reviews", "PC building"], "markets": ["DE"], "platforms": ["youtube"],
         "follower_min": 50000, "follower_max": 250000},
        {"title": "CS2 & Valorant on TikTok",
         "description": "FPS players on TikTok with 4k+ followers; their young audience wants a better PC for competitive play.",
         "query": "", "tags": ["FPS gaming", "Esports"], "markets": ["FI", "DE"], "platforms": ["tiktok"],
         "follower_min": 4000, "follower_max": None},
        {"title": "Gaming setup & streaming creators",
         "description": "Creators who show off desks and streaming gear: a natural home for a 'my new PC' video.",
         "query": "", "tags": ["Gaming setup", "Streaming setup"], "markets": ["FI", "DE"], "platforms": ["youtube", "tiktok"],
         "follower_min": 5000, "follower_max": None},
        {"title": "Second-hand & sustainable tech",
         "description": "Creators into refurbishing, used deals and e-waste: they match Prenew's sustainability story.",
         "query": "", "tags": ["Sustainable tech"], "markets": ["DE", "FI"], "platforms": ["youtube", "tiktok", "instagram"],
         "follower_min": 1000, "follower_max": None},
        {"title": "Hidden gems: tiny but loyal",
         "description": "Finnish gaming creators under 10k followers with unusually engaged audiences; cheap and trusted.",
         "query": "", "tags": ["Budget gaming", "Gaming setup"], "markets": ["FI"], "platforms": ["youtube", "tiktok"],
         "follower_min": 500, "follower_max": 10000},
    ],
}

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
    "markets": ["FI", "DE"],
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
