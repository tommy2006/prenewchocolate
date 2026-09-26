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
    # Structured context the AI judges fit against (editable in "Brand profile").
    "profile": None,  # filled from PRENEW_PROFILE below
    "seed_version": 3,
}

# Prenew's first creator types (before we had their collaboration history); replaced on upgrade.
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

# Who the company is and who it wants to reach. The AI scores "fit" against this.
GOALS = {"sales": "Sales", "balanced": "Balanced", "awareness": "Awareness"}
DEFAULT_PROFILE = {
    "website": "",
    "target_customer": "",   # who buys, and who watches
    "min_audience_age": None,  # audiences clearly younger than this are a poor fit
    "price_range": "",
    "competitors": [],       # a creator sponsored by one of these is flagged
    "values": "",            # tone and what the brand stands for
    "no_go": [],             # never work with these kinds of creators
    "budget_max": None,      # EUR per collaboration
    "goal": "balanced",      # sales | balanced | awareness: changes how fit and audience quality are weighed
}
# Prenew's starting profile, from their brief. Competitors are an editable first guess.
PRENEW["profile"] = {
    **DEFAULT_PROFILE,
    "target_customer": "Gamers who want a capable gaming PC but find new ones too expensive, and parents buying "
                       "a first gaming PC for a teenager. Buyers are mostly 16-35.",
    "min_audience_age": 13,
    "competitors": ["Back Market", "refurbed", "Verkkokauppa.com", "Jimm's PC-Store", "Gigantti"],
    "values": "Trust (every PC is tested and comes with a warranty), value for money, and less e-waste than buying new.",
    "no_go": ["Gambling or skin betting", "Adult content"],
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
    co.pop("suggested_searches", None)  # replaced by recent searches
    co.pop("suggesting", None)
    for key in ("follower_min", "follower_max"):
        co["search"].setdefault(key, None)
    if co.get("scout_off") is None:
        # The web scout runs paid Claude web searches; it's opt-in per search now, never left on by default.
        co["search"]["ai_scout"] = False
        co["scout_off"] = True
    co["profile"] = {**DEFAULT_PROFILE, **(co.get("profile") or {})}
    if co.get("id") == PRENEW["id"] and co.get("seed_version", 1) < PRENEW["seed_version"]:
        if co.get("seed_version", 1) < 2:
            # Creator types based on Prenew's real collaborations; keep anything the user added.
            own_tags = [t for t in co.get("suggested_tags", []) if t not in _OLD_PRENEW_TAGS]
            co["suggested_tags"] = list(dict.fromkeys(PRENEW["suggested_tags"] + own_tags))
        # Fill the brand profile, but never overwrite something the user typed.
        co["profile"] = {k: co["profile"][k] if co["profile"][k] not in (None, "", []) else v
                         for k, v in PRENEW["profile"].items()}
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
