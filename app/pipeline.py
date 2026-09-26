"""One discovery run: plan searches -> scrape platforms -> compute metrics -> score with the chosen AI."""
import asyncio
import logging

import httpx

from . import config, llm, metrics, settings
from .images import cache_creator_images
from .markets import MARKETS
from .sources import instagram, tiktok, youtube
from .store import now_iso, store

log = logging.getLogger("scout")

ACTIVE_DAYS = 120  # ignore creators who haven't posted in ~4 months


def _step(job: dict, key: str, label: str, status: str = "running", detail: str = "") -> None:
    for s in job["steps"]:
        if s["key"] == key:
            s.update(label=label, status=status, detail=detail)
            break
    else:
        job["steps"].append({"key": key, "label": label, "status": status, "detail": detail})
    job["updated_at"] = now_iso()


def _clamp(value, default: int) -> int:
    """0-100 int; tolerates "85" or 85.0 from less strict models, and uses `default` for anything unreadable."""
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return default


def outside_markets(creator: dict, markets: list[str]) -> bool:
    """True if the creator is clearly based elsewhere. Platform search only *biases* toward a country,
    so this drops obvious outsiders before paying to score them. English is kept: many local creators use it."""
    langs = {lang for m in markets if m in MARKETS for lang in MARKETS[m]["languages"]}
    country, lang = creator.get("country") or "", creator.get("language") or ""
    return bool((country and country not in markets) or (lang and lang != "en" and lang not in langs))


def build_match(creator: dict, r: dict, job_id: str, markets: list[str] | None = None) -> dict:
    niche = _clamp(r.get("niche_fit"), 0)
    market = _clamp(r.get("market_fit"), 50)
    safety = _clamp(r.get("brand_safety"), 100)
    eng, act = creator.get("engagement_score", 40), creator.get("activity_score", 30)
    score = 0.40 * niche + 0.20 * market + 0.25 * eng + 0.10 * act + 0.05 * safety
    if r.get("competitor_sponsor"):
        score -= 15
    if safety < 50:
        score -= 15
    followers = creator.get("followers") or 0
    return {
        "score": _clamp(round(score), 0),
        "niche_fit": niche,
        "market_fit": market,
        "brand_safety": safety,
        "engagement": eng,
        "activity": act,
        "language": (r.get("language") or creator.get("language") or "")[:2].lower(),
        "country": (r.get("country") or creator.get("country") or "")[:2].upper(),
        "summary": r.get("summary", ""),
        "niche": str(r.get("niche") or "")[:40],
        "games": [str(g) for g in (r.get("games") or []) if g][:6],
        "tags": r.get("tags", [])[:5],
        "matched_tags": r.get("matched_tags", []),
        "why": r.get("why", [])[:3],
        "red_flags": r.get("red_flags", []),
        "competitor_sponsor": bool(r.get("competitor_sponsor")),
        "hidden_gem": followers < 50_000 and eng >= 65 and niche >= 75,
        "status": None,
        "pitch": None,
        "job_id": job_id,
        "search_markets": markets or [],  # markets the search targeted; used when the country is unknown
        "created_at": now_iso(),
    }


async def _run_source(job, key, label, coro):
    _step(job, key, label)
    try:
        found = await coro
        _step(job, key, label, "done", f"{len(found)} creators")
        return found
    except Exception as e:  # one broken source shouldn't kill the run
        log.exception("source %s failed", key)
        _step(job, key, label, "error", str(e)[:160])
        return []


async def _scout(http, job, company, market, platforms):
    status = settings.source_status()
    found = await llm.web_scout(company, job, market, platforms)
    label = f"AI web scout ({market})"
    out = []
    by_platform = {p: [f["handle"] for f in found if f["platform"] == p] for p in platforms}
    if by_platform.get("youtube") and status["youtube"]:
        out += await youtube.lookup_handles(http, by_platform["youtube"], label)
    if by_platform.get("tiktok") and status["tiktok"]:
        out += await tiktok.lookup_handles(http, by_platform["tiktok"], label)
    if by_platform.get("instagram") and status["instagram"]:
        out += await instagram.lookup_handles(http, by_platform["instagram"], label)
    return out


async def run_job(job_id: str) -> None:
    job = store.jobs[job_id]
    company = store.companies[job["company_id"]]
    job["status"] = "running"
    fmin, fmax = job.get("follower_min"), job.get("follower_max")
    platforms = [p for p in job["platforms"] if settings.source_status().get(p)]
    ai = settings.ai_config()
    job["ai"] = f"{ai['label']} · {ai['model']}"
    markets = [m for m in job["markets"] if m in MARKETS]
    try:
        _step(job, "plan", "Planning local-language searches")
        plans = await llm.plan_searches(company, {**job, "markets": markets}, platforms)
        n_queries = sum(len(p["youtube_queries"]) + len(p["tiktok_queries"]) + len(p["tiktok_hashtags"])
                        + len(p["instagram_hashtags"]) for p in plans)
        _step(job, "plan", "Planning local-language searches", "done", f"{n_queries} searches across {len(plans)} markets")
        job["plan"] = plans

        async with httpx.AsyncClient() as http:
            tasks = []
            for plan in plans:
                m = plan["market"]
                lang = MARKETS[m]["languages"][0]
                if "youtube" in platforms and plan["youtube_queries"]:
                    tasks.append(_run_source(job, f"yt_{m}", f"YouTube · {MARKETS[m]['name']}",
                                             youtube.discover(http, plan["youtube_queries"], m, lang, fmin, fmax)))
                if "tiktok" in platforms and (plan["tiktok_queries"] or plan["tiktok_hashtags"]):
                    tasks.append(_run_source(job, f"tt_{m}", f"TikTok · {MARKETS[m]['name']}",
                                             tiktok.discover(http, plan["tiktok_queries"], plan["tiktok_hashtags"], m, fmin, fmax)))
                if "instagram" in platforms and plan["instagram_hashtags"]:
                    tasks.append(_run_source(job, f"ig_{m}", f"Instagram · {MARKETS[m]['name']}",
                                             instagram.discover(http, plan["instagram_hashtags"], m, fmin, fmax)))
                if job.get("ai_scout") and ai["web_search"]:
                    tasks.append(_run_source(job, f"ai_{m}", f"AI web scout · {MARKETS[m]['name']}",
                                             _scout(http, job, company, m, platforms)))
                elif job.get("ai_scout"):
                    _step(job, f"ai_{m}", f"AI web scout · {MARKETS[m]['name']}", "skipped", f"needs Claude, not {ai['label']}")
            results = await asyncio.gather(*tasks)

            candidates: dict[str, dict] = {}
            for found in results:
                for c in found:
                    if c["id"] in candidates:
                        candidates[c["id"]]["found_via"] = sorted(set(candidates[c["id"]]["found_via"] + c["found_via"]))
                    else:
                        candidates[c["id"]] = c
            job["found"] = len(candidates)

            _step(job, "filter", "Checking size, activity, engagement and market")
            already = store.matches.get(company["id"], {})
            pool, outside = [], 0
            for c in candidates.values():
                metrics.compute(c)
                if not metrics.in_range(c.get("followers"), fmin, fmax):
                    continue
                if c.get("days_since_last_post") is None or c["days_since_last_post"] > ACTIVE_DAYS:
                    continue
                if c["id"] in already:
                    continue
                if outside_markets(c, markets):
                    outside += 1
                    continue
                pool.append(c)
            pool.sort(key=metrics.prescore, reverse=True)
            pool = pool[:config.MAX_SCORE_PER_JOB]
            job["outside"] = outside
            detail = f"{len(pool)} of {len(candidates)} are active, in range and new"
            if outside:
                detail += f"; {outside} from other countries skipped"
            _step(job, "filter", "Checking size, activity, engagement and market", "done", detail)

            sem = asyncio.Semaphore(12)
            await asyncio.gather(*(cache_creator_images(http, c, sem) for c in pool))

        for c in pool:
            prev = store.creators.get(c["id"], {})
            c["found_via"] = sorted(set(prev.get("found_via", []) + c["found_via"]))
            c["fetched_at"] = now_iso()
            store.creators[c["id"]] = c
        store.save()

        await score_pool(job, company, pool, ai)
        job["status"] = "done"
    except Exception as e:
        log.exception("job %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(e)[:300]
    finally:
        job["finished_at"] = now_iso()
        company["last_job_id"] = job_id
        store.save()


MIN_MARKET_FIT = 35  # below this the AI judged the audience to be clearly outside the chosen markets


async def score_pool(job: dict, company: dict, pool: list[dict], ai: dict) -> None:
    """Score creators in batches. Creators whose batch fails are kept in job["unscored"] for a retry."""
    job_id = job["id"]
    job["to_score"] = len(pool)
    job["scored"] = 0
    job["unscored"] = []
    job.pop("score_error", None)
    label = f"Scoring fit with {ai['label']}"
    _step(job, "score", label, detail=f"0 / {len(pool)}")
    company_matches = store.matches.setdefault(company["id"], {})
    # Claude handles parallel batches well; free tiers elsewhere get overloaded, so go gentler.
    sem = asyncio.Semaphore(config.SCORE_CONCURRENCY if ai["kind"] == "anthropic" else 2)
    outside = 0

    async def score(batch):
        nonlocal outside
        async with sem:
            try:
                results = await llm.score_batch(company, job, batch)
            except Exception as e:
                log.warning("scoring batch failed: %s", e)
                job["score_error"] = str(e)[:240]
                results = None
        for c in batch:
            r = (results or {}).get(c["id"])
            if r is None:
                job["unscored"].append(c["id"])
                continue
            if not c.get("language") and r.get("language"):
                c["language"] = str(r["language"])[:2].lower()
            match = build_match(c, r, job_id, job["markets"])
            if match["market_fit"] < MIN_MARKET_FIT:
                outside += 1
                continue
            company_matches[c["id"]] = match
        job["scored"] += len(batch)
        _step(job, "score", label, detail=f"{job['scored']} / {len(pool)}")
        store.save()

    size = ai.get("batch_size", config.SCORE_BATCH_SIZE)
    await asyncio.gather(*(score(pool[i:i + size]) for i in range(0, len(pool), size)))
    new = sum(1 for m in company_matches.values() if m.get("job_id") == job_id)
    override = llm.model_overrides.get(ai["provider"])
    job["new"] = new
    job["outside"] = job.get("outside", 0) + outside
    parts = [f"{new} creators ranked"]
    if outside:
        parts.append(f"{outside} judged outside your markets")
    if override:
        parts.append(f"used {override['model']} because {override['reason']}")
    if job["unscored"]:
        parts.append(f"{len(job['unscored'])} couldn't be scored: {job.get('score_error') or ai['label'] + ' failed'}")
    _step(job, "score", label, "error" if job["unscored"] and not new else "done", "; ".join(parts))


async def retry_scoring(job_id: str) -> None:
    """Score the creators a job couldn't score, without searching the platforms again."""
    job = store.jobs[job_id]
    company = store.companies[job["company_id"]]
    pool = [store.creators[cid] for cid in job.get("unscored", [])
            if cid in store.creators and not outside_markets(store.creators[cid], job["markets"])]
    ai = settings.ai_config()
    job["status"] = "running"
    earlier = job.get("new", 0)
    try:
        await score_pool(job, company, pool, ai)
        job["new"] = sum(1 for m in store.matches.get(company["id"], {}).values() if m.get("job_id") == job_id)
        job["status"] = "done"
    except Exception as e:
        log.exception("retry of job %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(e)[:300]
    finally:
        job["retried_from"] = earlier
        job["finished_at"] = now_iso()
        store.save()
