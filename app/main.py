"""HTTP API + static UI. Run: python -m uvicorn app.main:app --port 8000"""
import asyncio
import logging
import re

from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audience, config, export as exporter, linking, llm, localai, partners, query, rules, scoring, settings
from .checks import CheckError, check_youtube
from .markets import DEAL_TYPES, LANGUAGES, MARKETS, PLATFORMS, SEARCH_PLATFORMS, TIERS
from .metrics import agency_hint
from .sources import youtube
from .pipeline import (fetch_linked, merge_ai, rebuild, rescore_company, retry_scoring, run_job, search_of,
                       upgrade_library)
from .store import DEFAULT_PROFILE, DEFAULT_SEARCH, GOALS, new_id, now_iso, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Scout")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/img", StaticFiles(directory=config.IMG_DIR), name="img")
_tasks: dict[str, asyncio.Task] = {}  # job id -> the running search, so it can be stopped
upgrade_library()  # creators saved by older versions get the new audience metrics and scores


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
        # Image names are hashes of their source URL, so a file never changes: let the browser keep it.
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


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
        "reject_reasons": REJECT_REASONS,
        "sources": settings.source_status(),
        "ai": _ai_summary(),
    }


def _ai_summary() -> dict:
    ai, writer = settings.ai_config(), settings.writer_config()
    return {"provider": ai["provider"], "label": ai["label"], "model": ai["model"], "local": ai["local"],
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
    return data


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
    if company["profile"] != old_profile:
        rescore_company(company)  # goal, budget or competitors change how everyone ranks
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


def card(company: dict, c: dict, m: dict, partner_idx: dict | None = None) -> dict:
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
        "url": c.get("url"),
        "engagement_rate": c.get("engagement_rate"),
        "engagement_vs_typical": c.get("engagement_vs_typical"),
        "is_new": m.get("job_id") == company.get("last_job_id"),
        # Worked with this company before (from the imported tracker): their latest week, or True.
        "partner": ((partner["weeks"] or [True])[-1]) if partner else None,
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
    job: str = ""  # show exactly what one search found, ignoring the other filters
    ids: str = ""  # exactly these creators (the bulk selection), ignoring the other filters


def _rows(company_id: str, f: Filters) -> list[tuple[dict, dict]]:
    platforms_f, tiers_f, markets_f = set(_csv(f.platforms)), set(_csv(f.tiers)), set(_csv(f.markets))
    market_langs = {lang for mk in markets_f if mk in MARKETS for lang in MARKETS[mk]["languages"]}
    tags_f = [t.strip().lower() for t in _csv(f.tags) if t.strip()]
    terms = f.q.lower().split()
    ids_f = set(_csv(f.ids))
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
        if (f.fmin and followers < f.fmin) or (f.fmax and followers > f.fmax):
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
    return {
        "total": len(rows),
        "page": page,
        "pages": pages,
        "items": [card(company, c, m, idx) for c, m in chunk],
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
    return {
        "card": card(company, c, m),
        "creator": {k: v for k, v in c.items() if k not in drop},
        "match": m,
        # The same person on other platforms, when one profile links to the other.
        "linked": [{k: o.get(k) for k in ("id", "platform", "name", "handle", "url", "followers", "avg_views",
                                            "views_window", "emails")} for o in others],
        "partner": {"weeks": partner["weeks"], "collabs": partner["collabs"]} if partner else None,
        "agency": agency_hint(c) or bool(partner and partner["agency"]),
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
    jobs = sorted((j for j in store.jobs.values() if j["company_id"] == company_id), key=lambda j: j["created_at"], reverse=True)
    out, seen = [], set()
    for j in jobs:
        key = (tuple(sorted(j.get("tags") or [])), tuple(sorted(j["markets"])), tuple(sorted(j["platforms"])),
               j.get("follower_min"), j.get("follower_max"), (j.get("focus") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({k: j.get(k) for k in ("id", "tags", "markets", "platforms", "follower_min", "follower_max", "focus",
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
    except partners.TrackerError as e:
        raise HTTPException(400, str(e))
    company["partners"] = {"file": filename, "imported_at": now_iso(), "items": items}
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
    return {"file": p["file"], "imported_at": p["imported_at"], "count": len(p["items"]),
            "collabs": sum(i["collabs"] for i in p["items"])}


@app.get("/api/companies/{company_id}/recall")
async def recall(company_id: str):
    """How well Scout's ranking agrees with the team's own history: which past partners are in the
    library, and where they rank. A quick sanity check of the scoring on real data."""
    company = _company(company_id)
    items = (company.get("partners") or {}).get("items", [])
    if not items:
        return {"partners": 0}
    idx = partners.index(company)
    matches = store.matches.get(company_id, {})
    ranked = sorted(((m["score"], cid) for cid, m in matches.items() if cid in store.creators), reverse=True)
    position = {cid: i for i, (_, cid) in enumerate(ranked)}
    found = {}
    for cid, m in matches.items():
        c = store.creators.get(cid)
        p = partners.find(idx, c, m) if c else None
        if p and (p["name"] not in found or m["score"] > found[p["name"]]["score"]):
            found[p["name"]] = {"name": p["name"], "creator": c.get("name"), "id": cid, "score": m["score"],
                                "fit": m.get("fit"), "rank": position.get(cid, len(ranked)) + 1}
    rows = sorted(found.values(), key=lambda r: r["rank"])
    top = max(1, len(ranked) // 4)
    return {
        "partners": len(items),
        "library": len(ranked),
        "found": len(rows),
        "in_top_quarter": sum(1 for r in rows if r["rank"] <= top),
        "median_rank_pct": round(100 * sorted(r["rank"] for r in rows)[len(rows) // 2] / len(ranked)) if rows else None,
        "rows": rows[:30],
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


@app.post("/api/companies/{company_id}/jobs")
async def start_job(company_id: str, body: JobIn):
    company = _company(company_id)
    sources = settings.source_status()  # no AI set up is fine: planning uses templates, scores come from rules
    platforms = [p for p in (body.platforms or list(SEARCH_PLATFORMS)) if p in SEARCH_PLATFORMS and sources.get(p)]
    if not platforms:
        raise HTTPException(400, "None of the chosen platforms is set up yet. Add a YouTube key in Settings, or search TikTok.")
    markets = [m for m in body.markets if m in MARKETS]
    if not markets:
        raise HTTPException(400, "Pick at least one market to search in")
    running = [j for j in store.jobs.values() if j["company_id"] == company_id and j["status"] in ("queued", "running")]
    if running:
        raise HTTPException(409, "A search is already running for this company")
    # Size slider (or older size chips) -> follower range. Nothing picked = any size
    # (Prenew: "find influencers no matter the size").
    chosen = [t for t in TIERS if t[0] in body.tiers]
    if body.follower_min is not None or body.follower_max is not None:
        fmin, fmax = max(0, body.follower_min or 0), body.follower_max
    elif chosen:
        fmin = max(500, min(lo for _, lo, _, _ in chosen))
        fmax = None if any(hi is None for _, _, hi, _ in chosen) else max(hi for _, _, hi, _ in chosen)
    else:
        fmin, fmax = 1000, None
    company["search"] = SearchIn(**body.model_dump(exclude={"focus"})).model_dump()
    job = {
        "id": new_id("job"),
        "company_id": company_id,
        "focus": body.focus.strip(),
        "tags": body.tags,
        "platforms": platforms,
        "markets": markets,
        "follower_min": fmin,
        "follower_max": fmax,
        "deal_types": body.deal_types,
        "avoid": body.avoid,
        "example_creators": body.example_creators,
        "ai_scout": body.ai_scout,
        "status": "queued",
        "steps": [],
        "found": 0,
        "scored": 0,
        "to_score": 0,
        "created_at": now_iso(),
    }
    store.jobs[job["id"]] = job
    store.save()
    _run(job["id"], run_job(job["id"]))
    return job


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


@app.get("/api/settings")
async def get_settings():
    return settings.public()


@app.put("/api/settings")
async def put_settings(body: SettingsIn):
    if body.ai_provider and body.ai_provider not in settings.PROVIDERS:
        raise HTTPException(400, "Unknown AI provider")
    changes = body.model_dump()
    changes["providers"] = {k: v.model_dump() for k, v in body.providers.items()}
    settings.update(changes)
    llm.clear_overrides()  # a new key/model deserves a fresh try
    return settings.public()


class TestIn(BaseModel):
    target: str  # "ai" | "youtube"
    provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    workspace_id: str | None = None
    youtube_api_key: str | None = None


def _ai_overrides(body: "TestIn") -> dict:
    return {"api_key": body.api_key, "model": body.model, "base_url": body.base_url, "workspace_id": body.workspace_id}


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
            return {"ok": True, "message": await llm.test_ai(ai)}
        if body.target == "youtube":
            return {"ok": True, "message": await check_youtube(body.youtube_api_key or settings.youtube_key())}
    except (llm.LLMError, CheckError) as e:
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
        return {"ok": False, "message": str(e), "models": []}
    return {"ok": True, "models": models, "current": ai["model"],
            "recommended": llm.recommend_model(body.provider, models, ai["model"])}
