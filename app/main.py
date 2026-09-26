"""HTTP API + static UI. Run: python -m uvicorn app.main:app --port 8000"""
import asyncio
import csv
import io
import logging

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, llm, settings
from .checks import CheckError, check_apify, check_youtube
from .markets import DEAL_TYPES, LANGUAGES, MARKETS, PLATFORMS, TIERS
from .pipeline import retry_scoring, run_job
from .store import DEFAULT_SEARCH, new_id, now_iso, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Scout")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/img", StaticFiles(directory=config.IMG_DIR), name="img")
_background: set[asyncio.Task] = set()

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
        "tiers": [{"key": k, "min": lo, "max": hi, "label": label} for k, lo, hi, label in TIERS],
        "deal_types": DEAL_TYPES,
        "sources": settings.source_status(),
        "ai": _ai_summary(),
    }


def _ai_summary() -> dict:
    ai = settings.ai_config()
    return {"provider": ai["provider"], "label": ai["label"], "model": ai["model"],
            "ready": ai["ready"], "web_search": ai["web_search"]}


# --- Companies -------------------------------------------------------------------------------

class CompanyIn(BaseModel):
    name: str
    description: str = ""


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


async def _suggest(company: dict) -> list[str]:
    """Creator-type ideas from the company description. Never blocks company setup on failure."""
    if not settings.source_status()["ai"] or not company.get("description"):
        return []
    try:
        return await asyncio.wait_for(
            llm.suggest_tags(company["name"], company["description"], company["search"].get("tags", [])), 60)
    except Exception:
        logging.getLogger("scout").exception("tag suggestion failed")
        return []


async def _suggest_searches(company: dict) -> list[dict]:
    """Ready-made searches for the company. Never blocks company setup on failure."""
    if not settings.source_status()["ai"] or not company.get("description"):
        return []
    try:
        return await asyncio.wait_for(llm.suggest_searches(company), 90)
    except Exception:
        logging.getLogger("scout").exception("search suggestion failed")
        return []


def _company(company_id: str) -> dict:
    company = store.companies.get(company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    return company


@app.get("/api/companies")
async def list_companies():
    return sorted(store.companies.values(), key=lambda c: c.get("created_at", ""))


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
        "suggested_tags": [],
        "suggested_searches": [],
        "search": dict(DEFAULT_SEARCH),
        "created_at": now_iso(),
    }
    company["suggested_tags"] = await _suggest(company)
    company["suggested_searches"] = await _suggest_searches(company)
    store.companies[company["id"]] = company
    store.save()
    return company


@app.put("/api/companies/{company_id}")
async def update_company(company_id: str, body: CompanyIn):
    company = _company(company_id)
    changed = body.description.strip() != company.get("description")
    company["name"] = body.name.strip() or company["name"]
    company["description"] = body.description.strip()
    if changed:
        company["suggested_tags"] = await _suggest(company) or company.get("suggested_tags", [])
        company["suggested_searches"] = await _suggest_searches(company) or company.get("suggested_searches", [])
    store.save()
    return company


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


@app.post("/api/companies/{company_id}/suggest-searches")
async def more_searches(company_id: str):
    """More ready-made searches; new ones go first."""
    company = _company(company_id)
    have = company.get("suggested_searches", [])
    fresh = await llm.suggest_searches(company, count=4, avoid_titles=[s["title"] for s in have])
    company["suggested_searches"] = (fresh + have)[:12]
    store.save()
    return {"suggested_searches": company["suggested_searches"], "added": len(fresh)}


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


def card(company: dict, c: dict, m: dict) -> dict:
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
    }


SORTS = {
    "match": lambda cm: -cm[1]["score"],
    "gems": lambda cm: (not cm[1].get("hidden_gem"), -cm[1]["score"]),
    "views": lambda cm: -(cm[0].get("avg_views") or 0),
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
    status: str = ""
    sort: str = "match"
    fmin: int = 0  # size slider: followers from..to (0 = no limit)
    fmax: int = 0
    job: str = ""  # show exactly what one search found, ignoring the other filters


def _rows(company_id: str, f: Filters) -> list[tuple[dict, dict]]:
    platforms_f, tiers_f, markets_f = set(_csv(f.platforms)), set(_csv(f.tiers)), set(_csv(f.markets))
    market_langs = {lang for mk in markets_f if mk in MARKETS for lang in MARKETS[mk]["languages"]}
    tags_f = [t.strip().lower() for t in _csv(f.tags) if t.strip()]
    terms = f.q.lower().split()
    rows = []
    for cid, m in store.matches.get(company_id, {}).items():
        c = store.creators.get(cid)
        if not c:
            continue
        st = m.get("status")
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
    return {
        "total": len(rows),
        "page": page,
        "pages": pages,
        "items": [card(company, c, m) for c, m in chunk],
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
    return {
        "card": card(company, c, m),
        "creator": {k: v for k, v in c.items() if k not in drop},
        "match": m,
    }


class StatusIn(BaseModel):
    status: str | None


@app.patch("/api/companies/{company_id}/creators/{creator_id}")
async def set_status(company_id: str, creator_id: str, body: StatusIn):
    _, _, m = _pair(company_id, creator_id)
    if body.status not in (None, "hidden", *SHORTLIST_STATUSES):
        raise HTTPException(400, "Unknown status")
    m["status"] = body.status
    store.save()
    return {"status": m["status"]}


@app.post("/api/companies/{company_id}/creators/{creator_id}/pitch")
async def pitch(company_id: str, creator_id: str):
    company, c, m = _pair(company_id, creator_id)
    # Pitch with the criteria (deal types, markets…) of the search that found this creator.
    search = store.jobs.get(m.get("job_id")) or company.get("search", {})
    m["pitch"] = await llm.draft_pitch(company, search, c, m)
    store.save()
    return m["pitch"]


# Columns follow what Prenew asked for: country, subscribers, avg views (30/90 days), niche + games,
# contact details, then risks and trend.
EXPORT_COLUMNS = [
    ("Name", 26), ("Platform", 11), ("Profile URL", 40), ("Country", 9), ("Language", 10),
    ("Followers / subscribers", 14), ("Avg views", 12), ("Avg views period", 16), ("Views based on", 22),
    ("Views trend", 12), ("Trend", 11), ("Engagement rate %", 12), ("Engagement vs typical", 12),
    ("Posts per month", 10), ("Last post (days ago)", 10), ("Niche", 16), ("Games", 28), ("Tags", 36),
    ("Match score", 9), ("Niche fit", 9), ("Market fit", 9), ("Brand safety", 9), ("Risks / red flags", 44),
    ("Competitor sponsor", 10), ("Email", 30), ("Other contacts", 44), ("Summary", 60), ("Why they fit", 70),
    ("Status", 12), ("Found via", 40),
]


def _export_row(c: dict, m: dict) -> list:
    er = c.get("engagement_rate")
    trend = c.get("views_trend")
    socials = c.get("socials") or {}
    others = [f"{k}: {v}" for k, v in socials.items()] + [l for l in c.get("links", []) if l not in socials.values()]
    return [
        c.get("name"), PLATFORMS[c["platform"]], c.get("url"), m.get("country") or c.get("country") or "",
        LANGUAGES.get(m.get("language") or c.get("language") or "", m.get("language") or ""),
        c.get("followers"), c.get("avg_views"), c.get("views_window") or "", c.get("views_basis") or "",
        f"{trend:+.0%}" if trend is not None else "", c.get("trend") or "",
        round(er * 100, 2) if er is not None else "", c.get("engagement_vs_typical"),
        c.get("posts_per_month"), c.get("days_since_last_post"), m.get("niche") or "", ", ".join(m.get("games", [])),
        ", ".join(m.get("tags", [])), m["score"], m.get("niche_fit"), m.get("market_fit"), m.get("brand_safety"),
        "; ".join(m.get("red_flags", [])), "yes" if m.get("competitor_sponsor") else "",
        "; ".join(c.get("emails", [])), "; ".join(others[:6]), m.get("summary") or "", " | ".join(m.get("why", [])),
        m.get("status") or "", "; ".join(c.get("found_via", [])),
    ]


def _xlsx(company: dict, rows: list[tuple[dict, dict]]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Creators"
    ws.append([name for name, _ in EXPORT_COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="16161A")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for c, m in rows:
        ws.append(_export_row(c, m))
        link = ws.cell(row=ws.max_row, column=3)
        if link.value:
            link.hyperlink = link.value
            link.font = Font(color="1D4ED8", underline="single")
    for i, (_, width) in enumerate(EXPORT_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 32
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@app.get("/api/companies/{company_id}/export")
async def export(company_id: str, f: Annotated[Filters, Depends()], format: str = "xlsx"):
    """Download what the grid shows (or the shortlist, with status=shortlist) as Excel or CSV."""
    company = _company(company_id)
    rows = _rows(company_id, f)
    stem = f"{company['name'].lower().replace(' ', '-')}-{'shortlist' if f.status == 'shortlist' else 'creators'}"
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([name for name, _ in EXPORT_COLUMNS])
        w.writerows(_export_row(c, m) for c, m in rows)
        # BOM so Excel opens UTF-8 (ä, ö, ß) correctly
        return Response("﻿" + buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'})
    return Response(_xlsx(company, rows),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'})


# --- Discovery jobs --------------------------------------------------------------------------

class JobIn(SearchIn):
    focus: str = ""  # free text from the search box


@app.post("/api/companies/{company_id}/jobs")
async def start_job(company_id: str, body: JobIn):
    company = _company(company_id)
    sources = settings.source_status()
    if not sources["ai"]:
        raise HTTPException(400, "No AI is set up yet. Open Settings and add a key for the AI you want to use.")
    platforms = [p for p in (body.platforms or list(PLATFORMS)) if p in PLATFORMS and sources.get(p)]
    if not platforms:
        raise HTTPException(400, "None of the chosen platforms is set up yet. Add a YouTube key or an Apify token in Settings.")
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
    task = asyncio.create_task(run_job(job["id"]))
    _background.add(task)
    task.add_done_callback(_background.discard)
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
    task = asyncio.create_task(retry_scoring(job_id))
    _background.add(task)
    task.add_done_callback(_background.discard)
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
    providers: dict[str, ProviderIn] = {}
    youtube_api_key: str | None = None
    apify_token: str | None = None
    clear_youtube_api_key: bool = False
    clear_apify_token: bool = False


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
    target: str  # "ai" | "youtube" | "apify"
    provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    workspace_id: str | None = None
    youtube_api_key: str | None = None
    apify_token: str | None = None


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
                return {"ok": False, "message": "Add an API key and a model first"}
            return {"ok": True, "message": await llm.test_ai(ai)}
        if body.target == "youtube":
            return {"ok": True, "message": await check_youtube(body.youtube_api_key or settings.youtube_key())}
        if body.target == "apify":
            return {"ok": True, "message": await check_apify(body.apify_token or settings.apify_token())}
    except (llm.LLMError, CheckError) as e:
        return {"ok": False, "message": str(e)}
    raise HTTPException(400, "Unknown test")


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
