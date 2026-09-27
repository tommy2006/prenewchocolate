"""HTTP API + static UI. Run: python -m uvicorn app.main:app --port 8001"""
import asyncio
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (audience, auth, config, export as exporter, likeness, linking, llm, localai, marketmap, notify, partners,
               planner, query, rules, scoring, settings, tracker)
from .checks import CheckError, check_youtube
from .markets import DEAL_TYPES, LANGUAGES, MARKETS, PLATFORMS, SEARCH_PLATFORMS, TIERS
from .metrics import TYPICAL_RATE, TYPICAL_REACH, agency_hint, content_format, in_range, rising
from .sources import twitch, youtube
from .pipeline import (LINKED_LABEL, add_from_link, check_limit, draft_pitches, fetch_linked, find_contacts, found_by_search,
                       merge_ai, parse_profile_link, rebuild, refresh_numbers, rescore_company, retry_scoring, run_job,
                       run_task, run_tracker, search_of, upgrade_library)
from .store import DEFAULT_PROFILE, DEFAULT_SEARCH, GOALS, new_id, now_iso, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app):
    """Repeating searches run in the background for as long as Scout runs (see watches below)."""
    loop = asyncio.create_task(_watch_loop())
    yield
    loop.cancel()


app = FastAPI(title="Scout", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/img", StaticFiles(directory=config.IMG_DIR), name="img")
_tasks: dict[str, asyncio.Task] = {}  # job id -> the running search, so it can be stopped
upgrade_library()  # creators saved by older versions get the new audience metrics and scores
auth.admin_token()  # created at start, so scripts on the server can use the API right away


def _run(job_id: str, coro) -> None:
    task = asyncio.create_task(coro)
    _tasks[job_id] = task
    task.add_done_callback(lambda _: _tasks.pop(job_id, None))

SHORTLIST_STATUSES = ("shortlisted", "contacted", "replied", "declined")


@app.middleware("http")
async def no_cache_ui(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-store"
    elif request.url.path.startswith("/img/"):
        # Image names are hashes of their source URL, so a file never changes: let the browser keep it
        # (only the browser: images are behind the login).
        response.headers["Cache-Control"] = "private, max-age=604800, immutable"
    return response


NO_STORE = {"Cache-Control": "no-store"}
PUBLIC_PATHS = {"/api/login", "/api/logout", "/api/session"}
NEEDS_PASSWORD = ("Scout needs a password before other computers can use it. On the server, add the line "
                  "SCOUT_PASSWORD=your-password to Scout's .env file, then restart Scout.")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """With SCOUT_PASSWORD set, everything but the login and the UI's own code files needs a logged-in browser.
    Without it, only this computer is served. (Added last, so it runs before the other middleware.)"""
    path = request.url.path
    if path.startswith("/static/") or path in PUBLIC_PATHS:
        return await call_next(request)
    if auth.enabled():
        if path == "/" and request.query_params.get("pass"):  # a shareable link for judges: /?pass=...
            if auth.check_password(request.query_params["pass"]):
                return _logged_in(request, RedirectResponse("/", status_code=303, headers=NO_STORE))
            await asyncio.sleep(1)
        if auth.valid_session(request.cookies.get(auth.COOKIE)) or auth.is_admin(request):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Log in to Scout first"}, status_code=401, headers=NO_STORE)
        if path.startswith("/img/"):
            return Response(status_code=401, headers=NO_STORE)
        return FileResponse(config.STATIC_DIR / "login.html", headers=NO_STORE)
    if auth.is_local(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": NEEDS_PASSWORD}, status_code=403, headers=NO_STORE)
    return HTMLResponse(f'<!doctype html><meta charset="utf-8"><title>Scout</title>'
                        f'<p style="font: 16px system-ui; margin: 40px">{NEEDS_PASSWORD}</p>', status_code=403, headers=NO_STORE)


class LoginIn(BaseModel):
    password: str


@app.post("/api/login")
async def login(body: LoginIn, request: Request):
    if not auth.enabled():
        raise HTTPException(400, "This Scout has no password to log in with")
    if not auth.check_password(body.password):
        await asyncio.sleep(1)  # slows down guessing
        raise HTTPException(401, "Wrong password")
    return _logged_in(request, JSONResponse({"ok": True}))


def _logged_in(request: Request, response: Response) -> Response:
    """Give this browser the login cookie (30 days)."""
    https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(auth.COOKIE, auth.new_session(), max_age=auth.MAX_AGE, path="/", httponly=True,
                        samesite="lax", secure=https)
    return response


@app.post("/api/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(auth.COOKIE, path="/", httponly=True, samesite="lax")
    return response


@app.get("/api/session")
async def session_state(request: Request):
    """Whether this Scout has a password and this browser is logged in. `cookie_sent` tells an expired login
    apart from a proxy that drops cookies."""
    return {"auth": auth.enabled(), "logged_in": auth.valid_session(request.cookies.get(auth.COOKIE)),
            "cookie_sent": auth.COOKIE in request.cookies}


@app.exception_handler(llm.LLMError)
async def llm_error(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=502)


@app.get("/")
async def index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/api/meta")
async def meta():
    return {
        "markets": MARKETS,
        "languages": LANGUAGES,
        "platforms": PLATFORMS,
        "search_platforms": SEARCH_PLATFORMS,
        "tiers": [{"key": k, "min": lo, "max": hi, "label": label} for k, lo, hi, label in TIERS],
        "deal_types": DEAL_TYPES,
        "goals": GOALS,
        "fit_parts": scoring.FIT_PARTS,
        "quality_parts": {k: label for k, (label, _) in scoring.QUALITY_PARTS.items()},
        "quick_start": scoring.QUICK_START,
        "reject_reasons": REJECT_REASONS,
        "sources": settings.source_status(),
        "ai": _ai_summary(),
        "auth": auth.enabled(),  # a password is set: the UI offers "Log out"
    }


def _ai_summary() -> dict:
    ai, writer = settings.ai_config(), settings.writer_config()
    return {"provider": ai["provider"], "label": ai["label"], "model": ai["model"], "local": ai["local"],
            "check_limit": check_limit(ai),
            "ready": ai["ready"], "web_search": settings.scout_config() is not None,
            "writer": {"label": writer["label"], "model": writer["model"], "local": writer["local"]}}


# --- Companies -------------------------------------------------------------------------------

class ProfileIn(BaseModel):
    """Who the company wants to reach; the AI judges fit against it."""
    website: str = ""
    target_customer: str = ""
    min_audience_age: int | None = None
    price_range: str = ""
    competitors: list[str] = []
    values: str = ""
    no_go: list[str] = []
    budget_max: int | None = None
    goal: str = "balanced"
    usual_size: dict[str, list[int | None]] | None = None  # {"youtube": [50000, 250000], "tiktok": [4000, None]}


class CompanyIn(BaseModel):
    name: str
    description: str = ""
    profile: ProfileIn | None = None


def _clean_profile(p: ProfileIn | None, old: dict | None = None) -> dict:
    if p is None:
        return {**DEFAULT_PROFILE, **(old or {})}
    data = p.model_dump()
    data["goal"] = data["goal"] if data["goal"] in GOALS else "balanced"
    data["competitors"] = [c.strip() for c in data["competitors"] if c.strip()][:30]
    data["no_go"] = [c.strip() for c in data["no_go"] if c.strip()][:30]
    for key in ("min_audience_age", "budget_max"):
        data[key] = data[key] if data[key] and data[key] > 0 else None
    data["usual_size"] = clean_usual_size(data.get("usual_size"))
    return data


def clean_usual_size(raw) -> dict | None:
    """{platform: [min, max]} with positive whole numbers or None; platforms with no limits are dropped."""
    out = {}
    for platform, rng in (raw or {}).items():
        if platform not in PLATFORMS or not isinstance(rng, (list, tuple)):
            continue
        lo, hi = (list(rng) + [None, None])[:2]
        lo = int(lo) if isinstance(lo, (int, float)) and lo > 0 else None
        hi = int(hi) if isinstance(hi, (int, float)) and hi > 0 else None
        if lo and hi and hi < lo:
            lo, hi = hi, lo
        if lo or hi:
            out[platform] = [lo, hi]
    return out or None


def usual_range(company: dict, platform: str) -> tuple[int | None, int | None] | None:
    """The company's usual follower range on this platform, or None when it has none there."""
    rng = ((company.get("profile") or {}).get("usual_size") or {}).get(platform)
    return tuple(rng) if rng else None


class SearchIn(BaseModel):
    """What the user picked in the search area; saved per company."""
    tags: list[str] = []
    markets: list[str] = []
    platforms: list[str] = []
    tiers: list[str] = []
    follower_min: int | None = None  # size slider; None = no limit
    follower_max: int | None = None
    deal_types: list[str] = []
    avoid: list[str] = []
    example_creators: list[str] = []
    ai_scout: bool = False
    size_preset: str = ""  # "usual": the company's usual size per platform, from the brand profile


async def _fill_suggestions(company_id: str) -> None:
    """Creator types from the company description, written in the background:
    on a local model this takes a minute, and nobody should wait for it to add a company."""
    company = store.companies.get(company_id)
    if not company:
        return
    try:
        tags = await asyncio.wait_for(
            llm.suggest_tags(company["name"], company["description"], company["search"].get("tags", [])), 300)
        company["suggested_tags"] = tags or company.get("suggested_tags", [])
    except Exception:
        logging.getLogger("scout").exception("suggestions for %s failed", company_id)
    finally:
        company["suggesting"] = False
        store.save()


def _start_suggestions(company: dict) -> None:
    if settings.source_status()["ai"] and company.get("description"):
        company["suggesting"] = True
        _run(f"suggest_{company['id']}", _fill_suggestions(company["id"]))


def _company(company_id: str) -> dict:
    company = store.companies.get(company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    return company


def _public(company: dict) -> dict:
    """A company for the UI: the imported tracker as a short summary, not every row."""
    return {**company, "partners": _partners_summary(company)}


@app.get("/api/companies")
async def list_companies():
    return [_public(c) for c in sorted(store.companies.values(), key=lambda c: c.get("created_at", ""))]


@app.post("/api/companies")
async def create_company(body: CompanyIn):
    if not body.name.strip():
        raise HTTPException(400, "Company name is required")
    if not body.description.strip():
        raise HTTPException(400, "Describe what the company does")
    company = {
        "id": new_id("co"),
        "name": body.name.strip(),
        "description": body.description.strip(),
        "profile": _clean_profile(body.profile),
        "suggested_tags": [],
        "search": dict(DEFAULT_SEARCH),
        "created_at": now_iso(),
    }
    store.companies[company["id"]] = company
    _start_suggestions(company)
    store.save()
    return _public(company)


@app.put("/api/companies/{company_id}")
async def update_company(company_id: str, body: CompanyIn):
    company = _company(company_id)
    changed = body.description.strip() != company.get("description")
    company["name"] = body.name.strip() or company["name"]
    company["description"] = body.description.strip()
    old_profile = company.get("profile") or {}
    company["profile"] = _clean_profile(body.profile, old_profile)
    if changed:
        _start_suggestions(company)
    store.save()
    if {**company["profile"], "usual_size": None} != {**old_profile, "usual_size": None}:
        rescore_company(company)  # goal, budget or competitors change how everyone ranks (usual size only filters)
    return _public(company)


class WebsiteIn(BaseModel):
    url: str
    name: str = ""


@app.post("/api/profile-from-website")
async def profile_from_website(body: WebsiteIn):
    """Read the company's website and draft the brand profile (the user reviews it before saving)."""
    if not settings.source_status()["ai"]:
        raise HTTPException(400, "Set up an AI in Settings first")
    if not body.url.strip():
        raise HTTPException(400, "Enter the website address")
    return await llm.profile_from_website(body.url.strip(), body.name.strip())


@app.put("/api/companies/{company_id}/search")
async def save_search(company_id: str, body: SearchIn):
    company = _company(company_id)
    company["search"] = body.model_dump()
    store.save()
    return company["search"]


@app.delete("/api/companies/{company_id}")
async def delete_company(company_id: str):
    _company(company_id)
    if len(store.companies) == 1:
        raise HTTPException(400, "Keep at least one company")
    del store.companies[company_id]
    store.matches.pop(company_id, None)
    store.save()
    return {"ok": True}


@app.post("/api/companies/{company_id}/suggest-tags")
async def suggest_tags(company_id: str):
    """More creator-type ideas; new ones are added to the company's suggestions."""
    company = _company(company_id)
    have = company.get("suggested_tags", []) + company["search"].get("tags", [])
    fresh = await llm.suggest_tags(company["name"], company.get("description", ""), have)
    company["suggested_tags"] = company.get("suggested_tags", []) + fresh
    store.save()
    return {"suggested_tags": company["suggested_tags"], "added": fresh}


# --- Creators --------------------------------------------------------------------------------

def _csv(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


def _haystack(c: dict, m: dict) -> str:
    country = m.get("country") or c.get("country") or ""
    lang = m.get("language") or c.get("language") or ""
    parts = [
        c.get("name"), c.get("handle"), c.get("bio"), m.get("summary"), m.get("niche"), " ".join(m.get("games", [])),
        " ".join(m.get("tags", [])), " ".join(m.get("why", [])), PLATFORMS.get(c["platform"]),
        MARKETS.get(country, {}).get("name"), country, LANGUAGES.get(lang), c.get("category"),
        " ".join(p.get("title") or "" for p in c.get("recent_posts", [])[:10]),
    ]
    return " ".join(p for p in parts if p).lower()


def card(company: dict, c: dict, m: dict, partner_idx: dict | None = None, model: "likeness.Model | None" = None) -> dict:
    partner = partners.find(partner_idx if partner_idx is not None else partners.index(company), c, m)
    return {
        "id": c["id"],
        "platform": c["platform"],
        "name": c.get("name"),
        "handle": c.get("handle"),
        "cover": c.get("cover") or c.get("avatar"),
        "avatar": c.get("avatar"),
        "followers": c.get("followers"),
        "tier": c.get("tier"),
        "country": m.get("country") or c.get("country") or "",
        "language": m.get("language") or c.get("language") or "",
        "score": m["score"],
        "fit": m.get("fit", m["score"]),
        "quality": m.get("quality"),
        "checked": m.get("checked", "ai" if m.get("ai_checked") else "rules"),
        "confidence": (m.get("confidence") or {}).get("level"),
        "authenticity": (c.get("authenticity") or {}).get("score"),
        "median_views": c.get("median_views"),
        "price": c.get("price"),
        "summary": m.get("summary", ""),
        "niche": m.get("niche", ""),
        "games": m.get("games", [])[:3],
        "tags": m.get("tags", [])[:3],
        "avg_views": c.get("avg_views"),
        "views_window": c.get("views_window", ""),
        "trend": c.get("trend", ""),
        "views_trend": c.get("views_trend"),
        "hidden_gem": m.get("hidden_gem", False),
        "status": m.get("status"),
        "has_email": bool(c.get("emails")),
        "email": (c.get("emails") or [None])[0],
        "has_pitch": bool(m.get("pitch")),
        "rising": rising(c, m),
        # No email: where a message can still reach them.
        "contact_via": "" if c.get("emails") else ("Instagram DM" if (c.get("socials") or {}).get("instagram") or c["platform"] == "instagram"
                                                  else "TikTok DM" if c["platform"] == "tiktok" or (c.get("socials") or {}).get("tiktok")
                                                  else "Twitch or Discord" if c["platform"] == "twitch" else "No public contact"),
        "url": c.get("url"),
        "engagement_rate": c.get("engagement_rate"),
        "engagement_vs_typical": c.get("engagement_vs_typical"),
        "is_new": m.get("job_id") == company.get("last_job_id"),
        # Worked with this company before (from the imported tracker): their latest week, or True.
        "partner": ((partner["weeks"] or [True])[-1]) if partner else None,
        # How much they are like the past partners Scout found: {"score", "like": [names]} (None without a tracker).
        "likeness": likeness.card_value(model, c, m) if model is not None else None,
        "tips": {k: v for k, v in scoring.explain(c, m).items() if k in ("fit", "quality", "fit_word", "quality_word")},
    }


SORTS = {
    "match": lambda cm: -cm[1]["score"],
    "fit": lambda cm: (-cm[1].get("fit", 0), -cm[1]["score"]),
    "quality": lambda cm: (-(cm[1].get("quality") or 0), -cm[1]["score"]),
    "gems": lambda cm: (not cm[1].get("hidden_gem"), -cm[1]["score"]),
    "views": lambda cm: -(cm[0].get("median_views") or cm[0].get("avg_views") or 0),
    "trend": lambda cm: -(cm[0].get("views_trend") if cm[0].get("views_trend") is not None else -9),
    "engagement": lambda cm: -(cm[0].get("engagement_score") or 0),
    "followers_asc": lambda cm: cm[0].get("followers") or 0,
    "followers_desc": lambda cm: -(cm[0].get("followers") or 0),
    "newest": lambda cm: (cm[1].get("created_at") or "", cm[1]["score"]),
}


class Filters(BaseModel):
    """The grid's query: search-area choices plus result filters. Shared by the grid and the exports."""
    q: str = ""
    tags: str = ""
    platforms: str = ""
    tiers: str = ""
    markets: str = ""
    language: str = ""
    min_score: int = 0
    min_eng: int = 0
    has_email: bool = False
    gems: bool = False
    growing: bool = False
    status: str = ""
    sort: str = "match"
    fmin: int = 0  # size slider: followers from..to (0 = no limit)
    fmax: int = 0
    usual: bool = False  # the company's usual size per platform instead of the slider
    vmin: int = 0  # typical (median) views per post from..to (0 = no limit)
    vmax: int = 0
    rising: bool = False  # views up 50%+ in the last 30 days, and a good fit
    fmt: str = ""  # "long" | "short" | "live": what they mostly make
    age: str = ""  # "no_kids" | "adult": the likely audience age (game age ratings, what commenters say)
    job: str = ""  # show exactly what one search found, ignoring the other filters
    ids: str = ""  # exactly these creators (the bulk selection), ignoring the other filters


def _rows(company_id: str, f: Filters) -> list[tuple[dict, dict]]:
    platforms_f, tiers_f, markets_f = set(_csv(f.platforms)), set(_csv(f.tiers)), set(_csv(f.markets))
    market_langs = {lang for mk in markets_f if mk in MARKETS for lang in MARKETS[mk]["languages"]}
    tags_f = [t.strip().lower() for t in _csv(f.tags) if t.strip()]
    terms = f.q.lower().split()
    ids_f = set(_csv(f.ids))
    company = store.companies.get(company_id) or {}
    rows = []
    for cid, m in store.matches.get(company_id, {}).items():
        c = store.creators.get(cid)
        if not c:
            continue
        st = m.get("status")
        if ids_f:
            if cid in ids_f:
                rows.append((c, m))
            continue
        if f.job:
            if m.get("job_id") == f.job and st != "hidden":
                rows.append((c, m))
            continue
        if f.status == "shortlist" and st not in SHORTLIST_STATUSES:
            continue
        if f.status == "hidden" and st != "hidden":
            continue
        if f.status == "" and st == "hidden":
            continue
        if platforms_f and c["platform"] not in platforms_f:
            continue
        if tiers_f and c.get("tier") not in tiers_f:
            continue
        followers = c.get("followers") or 0
        if followers < config.MIN_FOLLOWERS:  # too small to work with, whatever the size filter says
            continue
        if f.usual:
            rng = usual_range(company, c["platform"])
            if rng and not in_range(followers, *rng):
                continue
        elif (f.fmin and followers < f.fmin) or (f.fmax and followers > f.fmax):
            continue
        if f.vmin or f.vmax:
            views = c.get("median_views") or c.get("avg_views")
            if views is None or (f.vmin and views < f.vmin) or (f.vmax and views > f.vmax):
                continue
        country = m.get("country") or c.get("country") or ""
        lang = m.get("language") or c.get("language") or ""
        # Unknown country: keep if they speak a market language or were found by a search for that market.
        if markets_f and country not in markets_f and not (
                not country and (lang in market_langs or markets_f & set(m.get("search_markets", [])))):
            continue
        if f.language and lang != f.language:
            continue
        if m["score"] < f.min_score or (c.get("engagement_score") or 0) < f.min_eng:
            continue
        if f.has_email and not c.get("emails"):
            continue
        if f.rising and not rising(c, m):
            continue
        if f.fmt and content_format(c) != f.fmt:
            continue
        if f.age:
            band = rules.age_estimate(c)["band"]
            if (f.age == "no_kids" and band == "young") or (f.age == "adult" and band != "older"):
                continue
        if f.gems and not m.get("hidden_gem"):
            continue
        if f.growing and (c.get("views_trend") is None or c["views_trend"] < 0.2):
            continue
        if tags_f or terms:
            hay = _haystack(c, m)
            # A creator type matches if the AI tagged the creator with it, or it appears in their content.
            if tags_f:
                own = {t.lower() for t in m.get("matched_tags", []) + m.get("tags", [])}
                if not any(t in own or t in hay for t in tags_f):
                    continue
            if not all(t in hay for t in terms):
                continue
        rows.append((c, m))
    if f.sort == "likeness":  # most like the past partners first
        model = likeness.Model(company, store.creators, store.matches.get(company_id, {}))
        score = {c["id"]: (likeness.card_value(model, c, m) or {}).get("score", 0) for c, m in rows}
        rows.sort(key=lambda cm: (-score[cm[0]["id"]], -cm[1]["score"]))
    else:
        rows.sort(key=SORTS.get(f.sort, SORTS["match"]))
    return rows


@app.get("/api/companies/{company_id}/creators")
async def list_creators(company_id: str, f: Annotated[Filters, Depends()], page: int = 1, page_size: int = 30):
    """The grid. With `job`, shows exactly what that search found and ignores the search-area filters."""
    company = _company(company_id)
    rows = _rows(company_id, f)
    page_size = max(1, min(page_size, 500))
    pages = max(1, -(-len(rows) // page_size))
    page = max(1, min(page, pages))
    chunk = rows[(page - 1) * page_size: page * page_size]
    idx = partners.index(company)
    model = likeness.Model(company, store.creators, store.matches.get(company_id, {}))
    return {
        "total": len(rows),
        "page": page,
        "pages": pages,
        "items": [card(company, c, m, idx, model) for c, m in chunk],
        "library_size": len(store.matches.get(company_id, {})),
    }


def _pair(company_id: str, creator_id: str) -> tuple[dict, dict, dict]:
    company = _company(company_id)
    m = store.matches.get(company_id, {}).get(creator_id)
    c = store.creators.get(creator_id)
    if not m or not c:
        raise HTTPException(404, "Creator not found")
    return company, c, m


@app.get("/api/companies/{company_id}/creators/{creator_id}")
async def creator_detail(company_id: str, creator_id: str):
    company, c, m = _pair(company_id, creator_id)
    drop = {"avatar_src", "cover_src"}
    ids = linking.groups(store.creators).get(creator_id, [creator_id])
    others = [o for o in linking.profiles(ids, store.creators).values() if o["id"] != creator_id and o["platform"] != c["platform"]]
    partner = partners.find(partners.index(company), c, m)
    model = likeness.Model(company, store.creators, store.matches.get(company_id, {}))
    return {
        "card": card(company, c, m, model=model),
        # "Like Kakkuh and Jyksedi: Minecraft, Finland, a similar size" (None without a looked-up tracker).
        "likeness": likeness.detail_value(model, c, m),
        "creator": {k: v for k, v in c.items() if k not in drop},
        "match": m,
        # The same person on other platforms, when one profile links to the other.
        "linked": [{k: o.get(k) for k in ("id", "platform", "name", "handle", "url", "followers", "avg_views",
                                            "views_window", "emails")} for o in others],
        "partner": {"weeks": partner["weeks"], "collabs": partner["collabs"]} if partner else None,
        "agency": agency_hint(c) or bool(partner and partner["agency"]),
        "explain": scoring.explain(c, m),
        # What's normal for an account of this size on this platform, for the reference lines in the stats window.
        "typical": {"rate": TYPICAL_RATE.get(c["platform"], {}).get(c.get("tier") or ""),
                    "reach": TYPICAL_REACH.get(c["platform"], {}).get(c.get("tier") or "")},
        "quality_notes": {k: {"sign": sign, "text": text} for k, (sign, text) in scoring.quality_notes(c).items()},
        # Who is likely watching: game age ratings and what commenters say, with example comments.
        "age": rules.age_estimate(c),
        "comment_clues": {k: rules.comment_quotes(c, k, 3) for k in ("young", "adult", "buying")},
    }


# Why the team says "not a fit": one tap, and the AI learns from it on the next search.
REJECT_REASONS = ["Wrong niche", "Audience too young", "Wrong market", "Too big or expensive", "Low-quality audience",
                  "Brand-safety concern", "Works with a competitor", "Other"]


class StatusIn(BaseModel):
    status: str | None
    reason: str = ""  # with "hidden": why they're not a fit


def _set_status(m: dict, body: StatusIn) -> None:
    if body.status not in (None, "hidden", *SHORTLIST_STATUSES):
        raise HTTPException(400, "Unknown status")
    m["status"] = body.status
    m["status_at"] = now_iso()
    if body.status == "hidden":
        m["feedback"] = body.reason.strip()[:120] or m.get("feedback")
    else:
        m.pop("feedback", None)


@app.patch("/api/companies/{company_id}/creators/{creator_id}")
async def set_status(company_id: str, creator_id: str, body: StatusIn):
    _, _, m = _pair(company_id, creator_id)
    _set_status(m, body)
    store.save()
    return {"status": m["status"]}


class BulkStatusIn(StatusIn):
    ids: list[str]


@app.post("/api/companies/{company_id}/creators/bulk-status")
async def bulk_status(company_id: str, body: BulkStatusIn):
    _company(company_id)
    matches = store.matches.get(company_id, {})
    done = 0
    for cid in body.ids[:500]:
        if cid in matches:
            _set_status(matches[cid], body)
            done += 1
    store.save()
    return {"updated": done}


@app.post("/api/companies/{company_id}/creators/{creator_id}/ai-check")
async def ai_check_one(company_id: str, creator_id: str):
    """Let the search AI re-score one creator that only has a quick score."""
    company, c, m = _pair(company_id, creator_id)
    ai = settings.ai_config()
    if not ai["ready"]:
        raise HTTPException(400, "No AI is set up yet. Open Settings.")
    search = store.jobs.get(m.get("job_id")) or {**company.get("search", {}), "id": m.get("job_id") or ""}
    results = await llm.score_batch(company, search, [c], ai)
    r = results.get(creator_id)
    if not r:
        raise HTTPException(502, "The AI didn't return a result for this creator. Try again.")
    match = rebuild(m, c, company, merge_ai(rules.quick_score(c, company, search), r))
    store.matches[company_id][creator_id] = match
    store.save()
    return match


@app.post("/api/companies/{company_id}/creators/{creator_id}/deep")
async def deep_evaluation(company_id: str, creator_id: str):
    """A thorough judgement of one creator: fresh comments, descriptions, sponsorship history, a verdict."""
    company, c, m = _pair(company_id, creator_id)
    if not settings.source_status()["ai"]:
        raise HTTPException(400, "No AI is set up yet. Open Settings.")
    if c["platform"] == "youtube" and not c.get("comment_sample") and settings.source_status().get("youtube"):
        async with httpx.AsyncClient() as http:
            try:
                c["comment_sample"] = await youtube.sample_comments(http, c, videos=3)
            except Exception as e:  # the evaluation still works from posts alone
                logging.getLogger("scout").info("comments for %s failed: %s", creator_id, e)
    audience.assess(c)
    search = search_of(m)
    r = await llm.deep_evaluate(company, search, c)
    match = rebuild(m, c, company, merge_ai(rules.quick_score(c, company, search), r))
    match["deep"] = {"at": now_iso(), "model": r.get("model"), "sponsors_seen": r.get("sponsors_seen", [])}
    store.matches[company_id][creator_id] = match
    store.save()
    return match


@app.post("/api/companies/{company_id}/creators/{creator_id}/pitch")
async def pitch(company_id: str, creator_id: str):
    company, c, m = _pair(company_id, creator_id)
    # Pitch with the criteria (deal types, markets…) of the search that found this creator.
    search = store.jobs.get(m.get("job_id")) or company.get("search", {})
    m["pitch"] = await llm.draft_pitch(company, search, c, m)
    store.save()
    return m["pitch"]


@app.get("/api/companies/{company_id}/export")
async def export(company_id: str, f: Annotated[Filters, Depends()], format: str = "xlsx"):
    """Download what the grid shows (or the shortlist, with status=shortlist) as Excel or CSV,
    in the layout of the company's collaboration tracker: one row per creator, platforms side by side."""
    company = _company(company_id)
    people = exporter.build_rows(company, _rows(company_id, f), store.creators, store.matches.get(company_id, {}))
    stem = f"{company['name'].lower().replace(' ', '-')}-{'shortlist' if f.status == 'shortlist' else 'creators'}"
    if format == "csv":
        return Response(exporter.to_csv(people), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})
    return Response(exporter.to_xlsx(people),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'})


# --- Search bar -----------------------------------------------------------------------------------

class QueryIn(BaseModel):
    q: str
    ai: bool = True  # also let the AI read what the rules didn't understand


@app.post("/api/companies/{company_id}/parse-query")
async def parse_query(company_id: str, body: QueryIn):
    """Plain words -> filters. Rules first (instant, free); the AI only for what's left over."""
    company = _company(company_id)
    known = list(dict.fromkeys(company.get("suggested_tags", []) + company["search"].get("tags", [])))
    out = query.parse(body.q, known)
    out["source"] = "rules"
    if body.ai and len(out["rest"]) >= 4 and settings.source_status()["ai"]:
        try:
            ai = await asyncio.wait_for(llm.parse_query(body.q, known), 60)
        except Exception as e:  # the rules' result is still useful
            logging.getLogger("scout").info("AI query parse failed: %s", e)
            return out
        f = out["filters"]
        tags = [str(t).strip() for t in ai.get("tags") or [] if str(t).strip()][:5]
        f["tags"] = list(dict.fromkeys((f.get("tags") or []) + tags))
        f["markets"] = list(dict.fromkeys((f.get("markets") or []) + [m for m in ai.get("markets") or [] if m in MARKETS]))
        f["platforms"] = list(dict.fromkeys((f.get("platforms") or []) + [p for p in ai.get("platforms") or [] if p in SEARCH_PLATFORMS]))
        for key in ("follower_min", "follower_max"):
            if not f.get(key) and (ai.get(key) or 0) > 0:
                f[key] = int(ai[key])
        if not f.get("language") and ai.get("language") in LANGUAGES:
            f["language"] = ai["language"]
        for flag in ("has_email", "growing", "gems"):
            f[flag] = f.get(flag) or bool(ai.get(flag))
        f = {k: v for k, v in f.items() if v not in (None, [], False, "")}
        out["filters"] = f
        out["rest"] = str(ai.get("rest") or "").strip()
        out["understood"] = query.describe(f)
        out["source"] = "ai"
    return out


@app.get("/api/companies/{company_id}/recent-searches")
async def recent_searches(company_id: str, limit: int = 8):
    """The last searches run for this company, to re-run with one click (duplicates merged)."""
    _company(company_id)
    jobs = sorted((j for j in store.jobs.values() if j["company_id"] == company_id and not j.get("mode")),
                  key=lambda j: j["created_at"], reverse=True)
    out, seen = [], set()
    for j in jobs:
        key = (tuple(sorted(j.get("tags") or [])), tuple(sorted(j["markets"])), tuple(sorted(j["platforms"])),
               j.get("follower_min"), j.get("follower_max"), j.get("size_preset") or "", (j.get("focus") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({k: j.get(k) for k in ("id", "tags", "markets", "platforms", "follower_min", "follower_max", "size_preset", "focus",
                                           "created_at", "new", "status")})
        if len(out) >= limit:
            break
    return out


# --- Past collaborations -----------------------------------------------------------------------

@app.post("/api/companies/{company_id}/partners")
async def import_partners(company_id: str, request: Request, filename: str = "tracker.xlsx"):
    """Upload the company's collaboration tracker (the raw file is the request body)."""
    company = _company(company_id)
    data = await request.body()
    if not data:
        raise HTTPException(400, "The file is empty")
    if len(data) > 10_000_000:
        raise HTTPException(400, "That file is too big (10 MB max)")
    try:
        items = partners.parse(data, filename)
        sheet = partners.sheet(data, filename)
    except partners.TrackerError as e:
        raise HTTPException(400, str(e))
    company["partners"] = {"file": filename, "imported_at": now_iso(), "items": items, "sheet": sheet}
    store.save()
    idx = partners.index(company)
    found = sum(1 for cid, m in store.matches.get(company_id, {}).items()
                if cid in store.creators and partners.find(idx, store.creators[cid], m))
    return {"partners": _partners_summary(company), "in_library": found}


@app.delete("/api/companies/{company_id}/partners")
async def remove_partners(company_id: str):
    company = _company(company_id)
    company.pop("partners", None)
    store.save()
    return {"ok": True}


def _partners_summary(company: dict) -> dict | None:
    p = company.get("partners")
    if not p:
        return None
    lookup = p.get("lookup") or {}
    return {"file": p["file"], "imported_at": p["imported_at"], "count": len(p["items"]),
            "collabs": sum(i["collabs"] for i in p["items"]), "looked_up_at": lookup.get("at"),
            "looked_up": sum(1 for r in (lookup.get("results") or {}).values() if r["status"] == "found")}


PART_NAMES = {"content": "content", "audience": "audience", "market": "market", "brand": "brand & safety",
              "readiness": "readiness & cost"}


_found_by_search = found_by_search


class PlanIn(BaseModel):
    budget: int = 5000  # EUR for the whole campaign
    goal: str = ""  # sales | balanced | awareness; "" = the brand profile's goal
    max_creators: int = 12
    need_email: bool = False
    min_fit: int = 55
    new_only: bool = False  # leave out creators the company already worked with


@app.post("/api/companies/{company_id}/plan")
async def plan_campaign(company_id: str, f: Annotated[Filters, Depends()], body: PlanIn):
    """The best mix of creators for a budget, from the list the grid shows (the same filters as the grid)."""
    company = _company(company_id)
    if body.budget < 50:
        raise HTTPException(400, "Plan with a budget of at least €50")
    goal = body.goal if body.goal in GOALS else scoring.goal_of(company)
    idx = partners.index(company)
    return planner.plan(_rows(company_id, f), store.creators, body.budget, goal, max(1, min(body.max_creators, 50)),
                        body.need_email, max(0, min(body.min_fit, 100)), lambda c, m: bool(partners.find(idx, c, m)),
                        body.new_only)


@app.get("/api/companies/{company_id}/market-map")
async def market_map(company_id: str):
    """Per market: creators by size, gems, past partners, emails, typical views and price, games, best matches."""
    company = _company(company_id)
    return marketmap.build(company, store.creators, store.matches.get(company_id, {}))


@app.get("/api/companies/{company_id}/partner-profile")
async def partner_profile(company_id: str):
    """What the past partners Scout found have in common: platforms, games, markets, size, rhythm."""
    company = _company(company_id)
    return likeness.profile(company, store.creators, store.matches.get(company_id, {}))


@app.get("/api/companies/{company_id}/recall")
async def recall(company_id: str):
    """How well Scout agrees with the team's own history.
    1. Which past partners Scout's own searches found, and where they rank (looking them up doesn't count).
    2. How Scout scores the past partners it could look up: they were picked by the brand, so most should
       score well; the lowest ones show where the scoring may be too harsh."""
    company = _company(company_id)
    items = (company.get("partners") or {}).get("items", [])
    if not items:
        return {"partners": 0}
    idx = partners.index(company)
    matches = store.matches.get(company_id, {})
    ranked = sorted(((m["score"], cid) for cid, m in matches.items() if cid in store.creators), reverse=True)
    position = {cid: i for i, (_, cid) in enumerate(ranked)}
    searched = [cid for cid in position if _found_by_search(store.creators[cid])]
    search_rank = {cid: i for i, cid in enumerate(searched)}  # rank among what the searches found
    found, scored = {}, {}
    for cid, m in matches.items():
        c = store.creators.get(cid)
        p = partners.find(idx, c, m) if c else None
        if not p:
            continue
        if (p["name"] not in scored or m["score"] > scored[p["name"]]["score"]):
            parts = m.get("fit_parts") or {}
            weakest = min(parts, key=parts.get) if parts else None
            scored[p["name"]] = {"name": p["name"], "creator": c.get("name"), "id": cid, "score": m["score"],
                                 "fit": m.get("fit"), "quality": m.get("quality"), "checked": m.get("checked", "rules"),
                                 "weakest": PART_NAMES.get(weakest, weakest), "weakest_score": parts.get(weakest)}
        if cid in search_rank and (p["name"] not in found or m["score"] > found[p["name"]]["score"]):
            found[p["name"]] = {"name": p["name"], "creator": c.get("name"), "id": cid, "score": m["score"],
                                "fit": m.get("fit"), "rank": search_rank[cid] + 1}
    rows = sorted(found.values(), key=lambda r: r["rank"])
    top = max(1, len(searched) // 4)
    fits = sorted(r["fit"] for r in scored.values() if r["fit"] is not None)
    lookup = (company["partners"].get("lookup") or {})
    statuses = [r["status"] for r in (lookup.get("results") or {}).values()]
    return {
        "partners": len(items),
        "library": len(searched),
        "found": len(rows),
        "in_top_quarter": sum(1 for r in rows if r["rank"] <= top),
        "median_rank_pct": round(100 * sorted(r["rank"] for r in rows)[len(rows) // 2] / len(searched)) if rows else None,
        "rows": rows[:30],
        "looked_up": bool(lookup),
        "lookup": {k: statuses.count(k) for k in ("found", "not_found", "twitch", "no_source")},
        "scores": {
            "count": len(fits),
            "median_fit": fits[len(fits) // 2] if fits else None,
            "fit_70": sum(1 for f in fits if f >= 70),
            "ai_checked": sum(1 for r in scored.values() if r["checked"] != "rules"),
            "lowest": sorted(scored.values(), key=lambda r: r["fit"] if r["fit"] is not None else 101)[:5],
        },
    }


@app.post("/api/companies/{company_id}/link-profiles")
async def link_profiles(company_id: str, limit: int = 30):
    """Fetch the other platform (YouTube <-> TikTok) of ranked creators who link to it, best first."""
    _company(company_id)
    ranked = sorted(store.matches.get(company_id, {}).items(), key=lambda kv: -kv[1]["score"])
    creators = [store.creators[cid] for cid, _ in ranked if cid in store.creators]
    added = await fetch_linked(creators, limit=limit)
    return {"added": added}


# --- Discovery jobs --------------------------------------------------------------------------

class JobIn(SearchIn):
    focus: str = ""  # free text from the search box


def _platforms(requested: list[str]) -> list[str]:
    sources = settings.source_status()  # no AI set up is fine: planning uses templates, scores come from rules
    platforms = [p for p in (requested or list(SEARCH_PLATFORMS)) if p in SEARCH_PLATFORMS and sources.get(p)]
    if not platforms:
        raise HTTPException(400, "None of the chosen platforms is set up yet. Add a YouTube key in Settings, or search TikTok.")
    return platforms


def _one_at_a_time(company_id: str) -> None:
    if any(j["company_id"] == company_id and j["status"] in ("queued", "running") for j in store.jobs.values()):
        raise HTTPException(409, "A search is already running for this company")


def _size_range(company: dict, body: SearchIn, platforms: list[str]) -> tuple[int | None, int | None, dict]:
    """(min, max, per-platform ranges) from the size picked in the search area. Nothing picked = any size
    (Prenew: "find influencers no matter the size")."""
    by_platform = {p: usual_range(company, p) for p in platforms} if body.size_preset == "usual" else {}
    by_platform = {p: list(r) for p, r in by_platform.items() if r}
    chosen = [t for t in TIERS if t[0] in body.tiers]
    if by_platform:
        # The company's usual size per platform; a platform without one is searched at any size (1k+).
        ranges = [by_platform.get(p, [1000, None]) for p in platforms]
        fmin = min(lo or 0 for lo, _ in ranges) or 1000
        fmax = None if any(hi is None for _, hi in ranges) else max(hi for _, hi in ranges)
    elif body.follower_min is not None or body.follower_max is not None:
        fmin, fmax = max(0, body.follower_min or 0), body.follower_max
    elif chosen:
        fmin = max(500, min(lo for _, lo, _, _ in chosen))
        fmax = None if any(hi is None for _, _, hi, _ in chosen) else max(hi for _, _, hi, _ in chosen)
    else:
        fmin, fmax = 1000, None
    return fmin, fmax, by_platform


def _new_job(company_id: str, platforms: list[str], markets: list[str], size: tuple, **extra) -> dict:
    fmin, fmax, by_platform = size
    job = {
        "id": new_id("job"),
        "company_id": company_id,
        "focus": "",
        "tags": [],
        "platforms": platforms,
        "markets": markets,
        "follower_min": fmin,
        "follower_max": fmax,
        "size_preset": "usual" if by_platform else "",
        "size_by_platform": by_platform,
        "deal_types": [],
        "avoid": [],
        "example_creators": [],
        "ai_scout": False,
        "status": "queued",
        "steps": [],
        "found": 0,
        "scored": 0,
        "to_score": 0,
        "created_at": now_iso(),
        **extra,
    }
    store.jobs[job["id"]] = job
    store.save()
    return job


@app.post("/api/companies/{company_id}/jobs")
async def start_job(company_id: str, body: JobIn):
    company = _company(company_id)
    platforms = _platforms(body.platforms)
    markets = [m for m in body.markets if m in MARKETS]
    all_markets = not markets  # "All markets": every market, with a lighter search in each (see pipeline)
    markets = markets or list(MARKETS)
    _one_at_a_time(company_id)
    company["search"] = SearchIn(**body.model_dump(exclude={"focus"})).model_dump()
    job = _new_job(company_id, platforms, markets, _size_range(company, body, platforms), all_markets=all_markets,
                   focus=body.focus.strip(), tags=body.tags, deal_types=body.deal_types, avoid=body.avoid,
                   example_creators=body.example_creators, ai_scout=body.ai_scout)
    _run(job["id"], run_job(job["id"]))
    return job


class SimilarIn(SearchIn):
    """Find more like these. source: "creators" (ids from the results), "partners" (the looked-up tracker)
    or "liked" (the "Creators you already like" field)."""
    source: str = "creators"
    ids: list[str] = []


@app.post("/api/companies/{company_id}/similar")
async def find_similar(company_id: str, body: SimilarIn):
    company = _company(company_id)
    platforms = _platforms(body.platforms)
    _one_at_a_time(company_id)
    matches = store.matches.get(company_id, {})
    seed_ids, handles = [], []
    if body.source == "partners":
        lookup = ((company.get("partners") or {}).get("lookup") or {}).get("results") or {}
        seed_ids = [cid for r in lookup.values() for cid in r["ids"] if cid in store.creators]
        if not seed_ids:
            raise HTTPException(400, "Look up the creators in your tracker first (Brand profile, Past collaborations)")
        label = "your past partners"
    elif body.source == "liked":
        handles = [h.strip() for h in (body.example_creators or company["search"].get("example_creators") or []) if h.strip()][:20]
        if not handles:
            raise HTTPException(400, "Add creators you like first (More filters, Creators you already like)")
        label = ", ".join(handles[:3]) + (f" and {len(handles) - 3} more" if len(handles) > 3 else "")
    else:
        seed_ids = [cid for cid in dict.fromkeys(body.ids) if cid in store.creators][:30]
        if not seed_ids:
            raise HTTPException(400, "Pick at least one creator to start from")
        names = [store.creators[cid].get("name") or cid for cid in seed_ids]
        label = ", ".join(names[:3]) + (f" and {len(names) - 3} more" if len(names) > 3 else "")
    # Same markets as the starting creators; else the markets picked in the search area.
    seed_markets = {(matches.get(cid) or {}).get("country") or store.creators[cid].get("country") for cid in seed_ids}
    markets = sorted(m for m in seed_markets if m in MARKETS) or [m for m in (body.markets or company["search"].get("markets") or []) if m in MARKETS]
    all_markets = not markets
    markets = markets or list(MARKETS)
    job = _new_job(company_id, platforms, markets, _size_range(company, body, platforms), mode="lookalike", all_markets=all_markets,
                   seed_ids=seed_ids, seed_handles=handles, seed_names=label, source=body.source,
                   deal_types=company["search"].get("deal_types") or [], avoid=company["search"].get("avoid") or [])
    _run(job["id"], run_job(job["id"]))
    return job


@app.post("/api/companies/{company_id}/tracker/lookup")
async def lookup_tracker(company_id: str):
    """Complete my tracker: find every creator of the uploaded tracker on YouTube and TikTok and score them."""
    company = _company(company_id)
    items = (company.get("partners") or {}).get("items") or []
    if not items:
        raise HTTPException(400, "Upload your collaboration tracker first (Brand profile, Past collaborations)")
    platforms = _platforms([])
    _one_at_a_time(company_id)
    markets = sorted({p["market"] for p in items if p.get("market") in MARKETS})
    job = _new_job(company_id, platforms, markets, (None, None, {}), mode="tracker")
    _run(job["id"], run_tracker(job["id"]))
    return job


@app.get("/api/companies/{company_id}/tracker/export")
async def export_tracker(company_id: str):
    """The uploaded tracker handed back, row for row, with the blanks Scout could fill filled in (highlighted)."""
    company = _company(company_id)
    if not (company.get("partners") or {}).get("items"):
        raise HTTPException(400, "Upload your collaboration tracker first")
    data = exporter.tracker_xlsx(company, store.creators, store.matches.get(company_id, {}))
    name = re.sub(r"[^\w.-]+", "_", (company["partners"].get("file") or "tracker.xlsx").rsplit(".", 1)[0])
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}_completed_by_Scout.xlsx"'})


# --- Repeating searches ("watches"): a saved search that runs again every day or week ---------------------------

WATCH_EVERY = {1: "every day", 7: "every week"}
MAX_WATCHES = 3  # per company: each run spends YouTube quota (about 500 units per market)
WATCH_CHECK_SECONDS = 600


class WatchIn(JobIn):
    every_days: int = 1


def _watch_label(s: dict) -> str:
    """"Finland, Estonia · YouTube + TikTok · Minecraft, Fortnite" for the list of repeating searches."""
    parts = [", ".join(MARKETS[m]["name"] for m in s.get("markets", []) if m in MARKETS),
             " + ".join(PLATFORMS.get(p, p) for p in (s.get("platforms") or SEARCH_PLATFORMS)),
             ", ".join(s.get("tags") or []), f"“{s['focus']}”" if s.get("focus") else ""]
    return " · ".join(p for p in parts if p)


def _due(w: dict) -> bool:
    last = datetime.fromisoformat(w.get("last_run_at") or w["created_at"])
    return datetime.now(timezone.utc) - last >= timedelta(days=w["every_days"]) - timedelta(minutes=30)


def _busy(company_id: str) -> bool:
    return any(j["company_id"] == company_id and j["status"] in ("queued", "running") for j in store.jobs.values())


def _run_watch(company: dict, w: dict) -> dict | None:
    """Start the watch's search now (without changing what the search area shows). None if it can't run."""
    body = JobIn(**w["search"])
    sources = settings.source_status()
    platforms = [p for p in (body.platforms or list(SEARCH_PLATFORMS)) if p in SEARCH_PLATFORMS and sources.get(p)]
    markets = [m for m in body.markets if m in MARKETS]
    if not platforms or not markets:
        return None
    job = _new_job(company["id"], platforms, markets, _size_range(company, body, platforms),
                   focus=body.focus.strip(), tags=body.tags, deal_types=body.deal_types, avoid=body.avoid,
                   example_creators=body.example_creators, ai_scout=False, watch_id=w["id"], auto=True)
    w["last_run_at"], w["last_job_id"] = now_iso(), job["id"]
    store.save()
    _run(job["id"], run_job(job["id"]))
    return job


async def _watch_loop() -> None:
    while True:
        await asyncio.sleep(WATCH_CHECK_SECONDS)
        try:
            for company in list(store.companies.values()):
                for w in company.get("watches", []):
                    if w.get("active") and _due(w) and not _busy(company["id"]):
                        _run_watch(company, w)
                        break  # one search at a time per company
        except Exception:
            logging.getLogger("scout").exception("repeating searches failed")


@app.get("/api/companies/{company_id}/watches")
async def list_watches(company_id: str):
    return [w for w in _company(company_id).get("watches", []) if w.get("active")]


@app.post("/api/companies/{company_id}/watches")
async def add_watch(company_id: str, body: WatchIn):
    """Repeat this search every day or week; new creators it finds land in the list (and show as new)."""
    company = _company(company_id)
    if body.every_days not in WATCH_EVERY:
        raise HTTPException(400, "Repeat every day (1) or every week (7)")
    if not [m for m in body.markets if m in MARKETS]:
        raise HTTPException(400, "Pick at least one market to search in")
    watches = company.setdefault("watches", [])
    if sum(1 for w in watches if w.get("active")) >= MAX_WATCHES:
        raise HTTPException(400, f"At most {MAX_WATCHES} repeating searches: stop one first")
    search = body.model_dump(exclude={"every_days"})
    w = {"id": new_id("watch"), "search": search, "every_days": body.every_days, "label": _watch_label(search),
         "every": WATCH_EVERY[body.every_days], "active": True, "created_at": now_iso(), "last_run_at": now_iso(),
         "last_job_id": None}
    watches.append(w)
    store.save()
    return w


@app.delete("/api/companies/{company_id}/watches/{watch_id}")
async def stop_watch(company_id: str, watch_id: str):
    company = _company(company_id)
    company["watches"] = [w for w in company.get("watches", []) if w["id"] != watch_id]
    store.save()
    return {"ok": True}


@app.post("/api/companies/{company_id}/watches/{watch_id}/run")
async def run_watch_now(company_id: str, watch_id: str):
    company = _company(company_id)
    w = next((w for w in company.get("watches", []) if w["id"] == watch_id and w.get("active")), None)
    if not w:
        raise HTTPException(404, "That repeating search doesn't exist anymore")
    _one_at_a_time(company_id)
    job = _run_watch(company, w)
    if not job:
        raise HTTPException(400, "None of this search's platforms or markets are available now")
    return job


class ForCreatorsIn(BaseModel):
    """Which creators a job works on: `ids`, or everyone on the shortlist or in the library."""
    ids: list[str] = []
    scope: str = ""  # "shortlist" | "all" | "" (= ids)
    redo: bool = False  # messages: rewrite the ones already drafted too


def _creator_ids(company_id: str, body: ForCreatorsIn) -> list[str]:
    matches = store.matches.get(company_id, {})
    if body.scope == "all":
        ids = [cid for cid, m in matches.items() if m.get("status") != "hidden"]
    elif body.scope == "shortlist":
        ids = [cid for cid, m in matches.items() if m.get("status") in SHORTLIST_STATUSES]
    else:
        ids = [cid for cid in dict.fromkeys(body.ids) if cid in matches]
    ids = [cid for cid in ids if cid in store.creators][:500]
    if not ids:
        raise HTTPException(400, "Pick at least one creator (or add some to the shortlist)")
    return ids


def _start_task(company_id: str, mode: str, work, body: ForCreatorsIn) -> dict:
    _company(company_id)
    ids = _creator_ids(company_id, body)
    _one_at_a_time(company_id)
    job = _new_job(company_id, [], [], (None, None, {}), mode=mode, ids=ids, redo=body.redo)
    _run(job["id"], run_task(job["id"], work))
    return job


class LinkIn(BaseModel):
    url: str


@app.post("/api/companies/{company_id}/add-creator")
async def add_creator(company_id: str, body: LinkIn):
    """A creator from a YouTube, TikTok or Twitch link (a profile or one of their videos): looked up and scored."""
    company = _company(company_id)
    link = parse_profile_link(body.url)
    if not link:
        raise HTTPException(400, "Paste a YouTube, TikTok or Twitch link to a creator's profile or one of their videos")
    _one_at_a_time(company_id)
    markets = [m for m in (company.get("search") or {}).get("markets", []) if m in MARKETS]
    job = _new_job(company_id, [link[0]], markets, (None, None, {}), mode="add", link=list(link))
    _run(job["id"], run_task(job["id"], add_from_link))
    return job


@app.post("/api/companies/{company_id}/find-contacts")
async def start_find_contacts(company_id: str, body: ForCreatorsIn):
    """Look for emails on the link pages, websites and YouTube channel links of creators without one."""
    return _start_task(company_id, "contacts", find_contacts, body)


@app.post("/api/companies/{company_id}/pitches")
async def start_pitches(company_id: str, body: ForCreatorsIn):
    """Draft a first message (email and short DM, in their language) for each creator that has none yet."""
    if not settings.source_status()["ai"]:
        raise HTTPException(400, "No AI is set up yet. Open Settings.")
    return _start_task(company_id, "pitches", draft_pitches, body)


@app.post("/api/companies/{company_id}/refresh")
async def start_refresh(company_id: str, body: ForCreatorsIn):
    """Fetch today's followers, views and posts again; the AI's judgement is kept."""
    return _start_task(company_id, "refresh", refresh_numbers, body)


@app.post("/api/jobs/{job_id}/retry-scoring")
async def retry_job_scoring(job_id: str):
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] in ("queued", "running"):
        raise HTTPException(409, "This search is still running")
    if not job.get("unscored"):
        raise HTTPException(400, "Nothing left to score")
    if not settings.source_status()["ai"]:
        raise HTTPException(400, "No AI is set up yet. Open Settings and add a key for the AI you want to use.")
    job["status"] = "queued"
    _run(job_id, retry_scoring(job_id))
    return job


@app.post("/api/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    """Stop a running search. Creators already scored stay in the results."""
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    task = _tasks.get(job_id)
    if task and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), 10)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    elif job["status"] in ("queued", "running"):  # e.g. left over from a restart
        job["status"] = "stopped"
        store.save()
    return job


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/companies/{company_id}/jobs/latest")
async def latest_job(company_id: str):
    jobs = [j for j in store.jobs.values() if j["company_id"] == company_id]
    return max(jobs, key=lambda j: j["created_at"]) if jobs else None


# --- Settings --------------------------------------------------------------------------------

class ProviderIn(BaseModel):
    api_key: str | None = None  # empty = keep the saved key
    model: str | None = None
    base_url: str | None = None
    workspace_id: str | None = None  # Claude organization-wide keys only
    clear_key: bool = False


class SettingsIn(BaseModel):
    ai_provider: str | None = None
    writer_provider: str | None = None  # "" = the search AI also writes messages
    providers: dict[str, ProviderIn] = {}
    youtube_api_key: str | None = None
    clear_youtube_api_key: bool = False
    twitch_client_id: str | None = None
    clear_twitch_client_id: bool = False
    twitch_client_secret: str | None = None
    clear_twitch_client_secret: bool = False
    notify_webhook: str | None = None
    clear_notify_webhook: bool = False


@app.get("/api/settings")
async def get_settings():
    return settings.public()


@app.put("/api/settings")
async def put_settings(body: SettingsIn):
    if body.ai_provider and body.ai_provider not in settings.PROVIDERS:
        raise HTTPException(400, "Unknown AI provider")
    changes = body.model_dump()
    changes["providers"] = {k: v.model_dump() for k, v in body.providers.items()}
    try:
        settings.update(changes)
    except settings.SettingsError as e:
        raise HTTPException(400, str(e))
    llm.clear_overrides()  # a new key/model deserves a fresh try
    return settings.public()


class TestIn(BaseModel):
    target: str  # "ai" | "youtube" | "twitch" | "webhook"
    provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    workspace_id: str | None = None
    youtube_api_key: str | None = None
    twitch_client_id: str | None = None
    twitch_client_secret: str | None = None
    notify_webhook: str | None = None


def _ai_overrides(body: "TestIn") -> dict:
    return {"api_key": body.api_key, "model": body.model, "base_url": body.base_url, "workspace_id": body.workspace_id}


def _key_hint(message: str, ai: dict) -> str:
    """Explain a failure at a new address that the saved key wasn't sent to."""
    if ai.get("key_withheld"):
        return (f"{message.rstrip('. ')}. The saved key only goes to the address it was saved with: "
                "type the key for this new address to test it.")
    return message


@app.post("/api/settings/test")
async def test_settings(body: TestIn):
    """Test what's typed in the form (falling back to saved values), without saving it."""
    try:
        if body.target == "ai":
            if body.provider not in settings.PROVIDERS:
                raise HTTPException(400, "Unknown AI provider")
            ai = settings.ai_config(body.provider, _ai_overrides(body))
            if not ai["ready"]:
                return {"ok": False, "message": "Download a model first" if ai["local"] else "Add an API key and a model first"}
            try:
                return {"ok": True, "message": await llm.test_ai(ai)}
            except llm.LLMError as e:
                return {"ok": False, "message": _key_hint(str(e), ai)}
        if body.target == "youtube":
            return {"ok": True, "message": await check_youtube(body.youtube_api_key or settings.youtube_key())}
        if body.target == "twitch":
            saved_id, saved_secret = settings.twitch_keys()
            client_id, secret = body.twitch_client_id or saved_id, body.twitch_client_secret or saved_secret
            if not client_id or not secret:
                return {"ok": False, "message": "Add both the Client ID and the Client Secret"}
            return {"ok": True, "message": await twitch.check(client_id, secret)}
        if body.target == "webhook":
            problem = await notify.send("Scout is connected: new creators from repeating searches will be posted here.",
                                        body.notify_webhook or None)
            return {"ok": not problem, "message": problem or "Sent a test message"}
    except (llm.LLMError, CheckError, twitch.TwitchError) as e:
        return {"ok": False, "message": str(e)}
    raise HTTPException(400, "Unknown test")


# --- Local AI (Ollama) -----------------------------------------------------------------------

_hardware: dict = {}


@app.get("/api/local-ai")
async def local_ai():
    """This computer, the model we recommend for it, what Ollama has, and any download in progress."""
    if not _hardware:
        _hardware.update(await asyncio.to_thread(localai.hardware))
    return {
        "hardware": _hardware,
        "recommended": localai.recommend(_hardware),
        "catalog": localai.CATALOG,
        "ollama": await localai.status(),
        "pull": localai.pull_state or None,
    }


class PullIn(BaseModel):
    model: str


@app.post("/api/local-ai/pull")
async def local_ai_pull(body: PullIn):
    """Download a model (only when the user presses Download)."""
    if not re.fullmatch(r"[\w.\-:/]{2,80}", body.model):
        raise HTTPException(400, "That isn't a model name")
    if localai.pull_state and not localai.pull_state.get("done"):
        raise HTTPException(409, f"Already downloading {localai.pull_state['model']}")
    if not (await localai.status())["running"]:
        raise HTTPException(400, "The local AI (Ollama) isn't running. Start it first.")
    _run("pull", localai.pull(body.model))
    await asyncio.sleep(0.3)
    return localai.pull_state


@app.post("/api/local-ai/start")
async def local_ai_start():
    if not localai.start():
        raise HTTPException(400, "Ollama isn't installed. Get it free from ollama.com/download, then try again.")
    for _ in range(20):
        await asyncio.sleep(0.5)
        if (await localai.status())["running"]:
            return {"ok": True}
    raise HTTPException(500, "Ollama didn't start. Open the Ollama app yourself.")


@app.post("/api/settings/models")
async def settings_models(body: TestIn):
    if body.provider not in settings.PROVIDERS:
        raise HTTPException(400, "Unknown AI provider")
    ai = settings.ai_config(body.provider, _ai_overrides(body))
    try:
        models = await llm.list_models(ai)
    except llm.LLMError as e:
        return {"ok": False, "message": _key_hint(str(e), ai), "models": []}
    return {"ok": True, "models": models, "current": ai["model"],
            "recommended": llm.recommend_model(body.provider, models, ai["model"])}
