"""One discovery run: plan searches -> scrape platforms -> compute metrics -> score with the chosen AI."""
import asyncio
import json
import logging

import httpx

from . import audience, config, linking, llm, lookalike, metrics, rules, scoring, settings, tracker
from .images import cache_creator_images
from .markets import MARKETS
from .sources import tiktok, twitch, youtube
from .store import now_iso, store

log = logging.getLogger("scout")

ACTIVE_DAYS = 120  # ignore creators who haven't posted in ~4 months
LINKED_LABEL = "Linked from their other profile"


def _step(job: dict, key: str, label: str, status: str = "running", detail: str = "") -> None:
    for s in job["steps"]:
        if s["key"] == key:
            s.update(label=label, status=status, detail=detail)
            break
    else:
        job["steps"].append({"key": key, "label": label, "status": status, "detail": detail})
    job["updated_at"] = now_iso()


def outside_markets(creator: dict, markets: list[str]) -> bool:
    """True if the creator is clearly based elsewhere. Platform search only *biases* toward a country,
    so this drops obvious outsiders before paying to score them. English is kept: many local creators use it."""
    langs = {lang for m in markets if m in MARKETS for lang in MARKETS[m]["languages"]}
    country, lang = creator.get("country") or "", creator.get("language") or ""
    return bool((country and country not in markets) or (lang and lang != "en" and lang not in langs))


def merge_ai(quick: dict, ai: dict) -> dict:
    """The AI's judgement on top of the quick score: whatever the AI left empty keeps the rules' value.
    Evidence: the AI's claims, plus the hard facts the rules read from the data (country, comments, email...)."""
    merged = {**quick, **{k: v for k, v in ai.items() if v not in (None, "", [])}}
    if ai.get("evidence"):
        seen = {(e["dim"], e["text"].lower()) for e in ai["evidence"]}
        merged["evidence"] = ai["evidence"] + [e for e in quick.get("evidence", [])
                                               if e.get("fact") and (e["dim"], e["text"].lower()) not in seen]
    merged["ai_checked"] = ai.get("ai_checked") or True
    return merged


def build_match(creator: dict, r: dict, job_id: str, markets: list[str] | None, company: dict) -> dict:
    goal = scoring.goal_of(company)
    parts = {
        "content": scoring.clamp(r.get("content_fit", r.get("niche_fit")), 0),
        "audience": scoring.clamp(r.get("audience_fit"), 50),
        "market": scoring.clamp(r.get("market_fit"), 50),
        "brand": scoring.clamp(r.get("brand_fit"), 70),
        "readiness": scoring.clamp(r.get("readiness"), 50),
    }
    safety = scoring.clamp(r.get("brand_safety"), 100)
    competitor = bool(r.get("competitor_sponsor"))
    q_parts = scoring.quality_parts(creator)
    checked = "deep" if r.get("ai_checked") == "deep" else "ai" if r.get("ai_checked") else "rules"
    evidence = [e for e in r.get("evidence") or [] if e.get("src") != "basis"]
    parts, basis, held = scoring.hold_back_unproven(parts, evidence, checked != "rules", r.get("unproven"))
    evidence = evidence + basis
    fit, quality = scoring.fit(parts, goal, competitor, safety), scoring.quality(q_parts)
    auth = creator.get("authenticity") or {}
    followers = creator.get("followers") or 0
    return {
        "score": scoring.overall(fit, quality, goal, q_parts["authenticity"]),
        "fit": fit,
        "quality": quality,
        "fit_parts": parts,
        "unproven": held,  # the AI's own number for parts held back because it cited nothing
        "quality_parts": q_parts,
        "goal": goal,
        "brand_safety": safety,
        "competitor_sponsor": competitor,
        "confidence": scoring.confidence(creator, checked),
        "evidence": evidence,
        # Plain lists for downloads and the hover text.
        "why": [e["text"] for e in evidence if e["sign"] == "+"][:3],
        "red_flags": [e["text"] for e in evidence if e["sign"] == "-"]
                     + [s["text"] for s in auth.get("signals", []) if s.get("penalty", 0) >= 12],
        "verdict": r.get("verdict", ""),
        "collab_idea": r.get("collab_idea", ""),
        "audience_note": r.get("audience_note", ""),
        "language": (r.get("language") or creator.get("language") or "")[:2].lower(),
        "country": (r.get("country") or creator.get("country") or "")[:2].upper(),
        "summary": r.get("summary", ""),
        "niche": str(r.get("niche") or "")[:40],
        "games": [str(g) for g in (r.get("games") or []) if g][:6],
        "tags": r.get("tags", [])[:5],
        "matched_tags": r.get("matched_tags", []),
        "hidden_gem": followers < 50_000 and parts["content"] >= 75 and q_parts["engagement"] >= 65 and q_parts["authenticity"] >= 60,
        "ai_checked": checked != "rules",
        "checked": checked,  # rules | ai | deep
        "status": None,
        "pitch": None,
        "v": scoring.VERSION,
        "job_id": job_id,
        "search_markets": markets or [],  # markets the search targeted; used when the country is unknown
        "created_at": now_iso(),
    }


def rebuild(match: dict, creator: dict, company: dict, r: dict) -> dict:
    """A new match from new scores, keeping what the team did with the old one (status, pitch, feedback...)."""
    new = build_match(creator, r, match.get("job_id"), match.get("search_markets") or [], company)
    for key in ("status", "pitch", "feedback", "created_at", "deep"):
        if match.get(key) is not None:
            new[key] = match[key]
    return new


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
    return out


async def _similar(http, job: dict, company: dict, platforms: list[str], size_of) -> list[dict]:
    """"Find more like these": the creators that the starting creators mention or feature."""
    status = settings.source_status()
    seeds = [store.creators[cid] for cid in job.get("seed_ids", []) if cid in store.creators]
    if job.get("seed_handles"):
        label = "Looking up the creators you like"
        _step(job, "seeds", label)
        fresh = await lookalike.seeds_from_handles(http, job["seed_handles"], status)
        for c in fresh:
            metrics.compute(c)
        _step(job, "seeds", label, "done", f"found {len(fresh)} profiles for {len(job['seed_handles'])} names")
        seeds += fresh
    if not seeds:
        raise ValueError("None of the starting creators could be found on YouTube or TikTok")
    if job.get("seed_handles"):
        job["seed_names"] = lookalike.seed_label(seeds)
    matched = store.matches.get(company["id"], {})
    known = {k for cid in matched if cid in store.creators for k in linking.own_keys(store.creators[cid])}
    return await lookalike.expand(http, seeds, platforms, size_of, known)


async def _youtube_seeds(http, queries: list[str], market: str, lang: str) -> list[dict]:
    found = await youtube.discover(http, queries, market, lang, None, None, max_channels=25)
    for c in found:
        c["_seed_only"] = True
    return found


async def _tiktok_from_youtube(http, job: dict, candidates: dict[str, dict]) -> list[dict]:
    """TikTok accounts that the YouTube channels found in this search link to."""
    handles = []
    for c in candidates.values():
        if c["platform"] == "youtube":
            key = linking.url_key("tiktok", (c.get("socials") or {}).get("tiktok", ""))
            handle = linking.lookup_handle(key) if key else ""
            if handle and f"tt_{handle}" not in candidates and handle not in handles:
                handles.append(handle)
    if not handles:
        return []
    label = "TikTok · linked from local YouTube channels"
    _step(job, "tt_links", label)
    try:
        found = await tiktok.lookup_handles(http, handles[:20], "TikTok linked from a YouTube channel in the search")
    except Exception as e:
        _step(job, "tt_links", label, "error", str(e)[:160])
        return []
    for c in found:
        metrics.compute(c)
    _step(job, "tt_links", label, "done", f"{len(found)} creators")
    return found


async def run_job(job_id: str) -> None:
    job = store.jobs[job_id]
    company = store.companies[job["company_id"]]
    job["status"] = "running"
    fmin, fmax = job.get("follower_min"), job.get("follower_max")
    by_platform = job.get("size_by_platform") or {}  # the company's usual size per platform, when picked

    def size_of(platform: str) -> tuple:
        return tuple(by_platform[platform]) if platform in by_platform else (fmin, fmax)

    platforms = [p for p in job["platforms"] if settings.source_status().get(p)]
    ai = settings.ai_config()
    job["ai"] = f"{ai['label']} · {ai['model']}" if ai["ready"] else "no AI (quick scores only)"
    markets = [m for m in job["markets"] if m in MARKETS]
    similar = job.get("mode") == "lookalike"
    try:
        plans = []
        if not similar:
            _step(job, "plan", "Planning local-language searches")
            plans, how = await _plan(company, {**job, "markets": markets}, platforms, ai)
            n_queries = sum(len(p["youtube_queries"]) + len(p["tiktok_queries"]) + len(p["tiktok_hashtags"]) for p in plans)
            if "twitch" in platforms:  # live streams in the language, plus a game and a channel search per creator type
                n_queries += len(plans) * (1 + 2 * len((job.get("tags") or company.get("suggested_tags", []))[:6]))
            _step(job, "plan", "Planning local-language searches", "done",
                  f"{n_queries} searches across {len(plans)} markets ({how})")
            job["plan"] = plans

        async with httpx.AsyncClient() as http:
            tasks = []
            if similar:
                tasks.append(_run_source(job, "similar", "Creators they mention or feature",
                                         _similar(http, job, company, platforms, size_of)))
            for plan in plans:
                m = plan["market"]
                lang = MARKETS[m]["languages"][0]
                if "youtube" in platforms and plan["youtube_queries"]:
                    tasks.append(_run_source(job, f"yt_{m}", f"YouTube · {MARKETS[m]['name']}",
                                             youtube.discover(http, plan["youtube_queries"], m, lang, *size_of("youtube"))))
                if "tiktok" in platforms and (plan["tiktok_queries"] or plan["tiktok_hashtags"]):
                    tasks.append(_run_source(job, f"tt_{m}", f"TikTok · {MARKETS[m]['name']}",
                                             tiktok.discover(http, plan["tiktok_queries"], plan["tiktok_hashtags"], m, *size_of("tiktok"))))
                    if "youtube" not in platforms and settings.source_status()["youtube"]:
                        # Local YouTubers often link their TikTok: a reliable way to find local TikTokers.
                        tasks.append(_run_source(job, f"yts_{m}", f"YouTube channels that link a TikTok · {MARKETS[m]['name']}",
                                                 _youtube_seeds(http, plan["tiktok_queries"][:2], m, lang)))
                if "twitch" in platforms:
                    # Twitch filters by broadcast language: live streams and channels for each creator type.
                    terms = job.get("tags") or company.get("suggested_tags", [])[:6]
                    tasks.append(_run_source(job, f"tw_{m}", f"Twitch · {MARKETS[m]['name']}",
                                             twitch.discover(http, terms, m, lang, *size_of("twitch"))))
                if job.get("ai_scout") and settings.scout_config():
                    tasks.append(_run_source(job, f"ai_{m}", f"AI web scout · {MARKETS[m]['name']}",
                                             _scout(http, job, company, m, platforms)))
                elif job.get("ai_scout"):
                    _step(job, f"ai_{m}", f"AI web scout · {MARKETS[m]['name']}", "skipped", "needs Claude in Settings")
            results = await asyncio.gather(*tasks)

            candidates: dict[str, dict] = {}
            for found in results:
                for c in found:
                    if c["id"] in candidates:
                        candidates[c["id"]]["found_via"] = sorted(set(candidates[c["id"]]["found_via"] + c["found_via"]))
                    else:
                        candidates[c["id"]] = c
            for c in candidates.values():
                metrics.compute(c)
            if "tiktok" in platforms:
                for c in await _tiktok_from_youtube(http, job, candidates):
                    candidates.setdefault(c["id"], c)
            seeds = [cid for cid, c in candidates.items() if c.pop("_seed_only", False)]
            for cid in seeds:  # YouTube wasn't asked for: those channels were only a way to their TikToks
                candidates.pop(cid)
            job["found"] = len(candidates)

            _step(job, "filter", "Checking size, activity, engagement and market")
            already = store.matches.get(company["id"], {})
            pool, outside = [], 0
            for c in candidates.values():
                if c["id"] in already:
                    # Known already: just remember this search found them too (the tracker check counts it).
                    prev = store.creators.get(c["id"])
                    if prev:
                        prev["found_via"] = sorted(set(prev.get("found_via", []) + c["found_via"]))
                    continue
                if not metrics.in_range(c.get("followers"), *size_of(c["platform"])):
                    continue
                if c.get("days_since_last_post") is None or c["days_since_last_post"] > ACTIVE_DAYS:
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
            await _comments_step(http, job, pool)

        for c in pool:
            audience.assess(c)
            prev = store.creators.get(c["id"], {})
            c["found_via"] = sorted(set(prev.get("found_via", []) + c["found_via"]))
            c["fetched_at"] = now_iso()
            store.creators[c["id"]] = c
        store.save()

        await score_pool(job, company, pool, ai)
        await _link_step(job, company)
        job["status"] = "done"
    except asyncio.CancelledError:
        _stopped(job)
    except Exception as e:
        log.exception("job %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(e)[:300]
    finally:
        job["finished_at"] = now_iso()
        company["last_job_id"] = job_id
        store.save()


async def run_tracker(job_id: str) -> None:
    """Complete my tracker: find each creator of the company's collaboration tracker on YouTube and TikTok,
    add them to the library and score them. Their numbers fill the tracker's blanks, and their scores are a
    sanity check of the scoring (these are creators the brand picked itself)."""
    job = store.jobs[job_id]
    company = store.companies[job["company_id"]]
    job["status"] = "running"
    items = (company.get("partners") or {}).get("items", [])
    status = settings.source_status()
    ai = settings.ai_config()
    job["ai"] = f"{ai['label']} · {ai['model']}" if ai["ready"] else "no AI (quick scores only)"
    try:
        label = f"Looking up the {len(items)} creators in your tracker"
        _step(job, "lookup", label, detail=f"0 / {len(items)}")
        async with httpx.AsyncClient() as http:
            results = await tracker.resolve_all(
                http, items, status, on_progress=lambda n: _step(job, "lookup", label, detail=f"{n} / {len(items)}"))
            found = list({c["id"]: c for r in results.values() for c in r["profiles"]}.values())
            for c in found:
                metrics.compute(c)
            counts = {k: sum(1 for r in results.values() if r["status"] == k) for k in ("found", "twitch")}
            detail = f"found {counts['found']} of {len(items)}"
            if counts["twitch"]:
                detail += f"; {counts['twitch']} only on Twitch (not searched)"
            _step(job, "lookup", label, "done", detail)
            matches = store.matches.setdefault(company["id"], {})
            pool = [c for c in found if c["id"] not in matches]
            sem = asyncio.Semaphore(12)
            await asyncio.gather(*(cache_creator_images(http, c, sem) for c in pool))
            await _comments_step(http, job, pool)
        fresh = {c["id"] for c in pool}
        for c in found:
            prev = store.creators.get(c["id"])
            if c["id"] in fresh:
                audience.assess(c)
                c["found_via"] = sorted(set((prev or {}).get("found_via", []) + c["found_via"]))
                c["fetched_at"] = now_iso()
                store.creators[c["id"]] = c
            elif prev:
                prev["found_via"] = sorted(set(prev.get("found_via", []) + c["found_via"]))
        company["partners"]["lookup"] = {
            "at": now_iso(),
            "results": {name: {"status": r["status"], "ids": [c["id"] for c in r["profiles"]], "sure": r["sure"], "how": r["how"]}
                        for name, r in results.items()},
        }
        job["partners_found"], job["partners_total"] = counts["found"], len(items)
        store.save()
        job["keep_all"] = True  # past partners stay in, whatever their market fit
        await score_pool(job, company, pool, ai)
        await _link_step(job, company)
        job["status"] = "done"
    except asyncio.CancelledError:
        _stopped(job)
    except Exception as e:
        log.exception("tracker lookup %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(e)[:300]
    finally:
        job["finished_at"] = now_iso()
        store.save()


async def _comments_step(http, job: dict, pool: list[dict]) -> None:
    """A sample of real comments per YouTube creator: who is watching, in what language, and whether
    they talk back (1 quota unit per video). TikTok doesn't show comments without a login."""
    yt = [c for c in pool if c["platform"] == "youtube"]
    if not yt or not settings.source_status().get("youtube"):
        return
    label = "Reading comments (audience language and quality)"
    _step(job, "comments", label)
    sem = asyncio.Semaphore(8)

    async def one(c):
        async with sem:
            try:
                c["comment_sample"] = await youtube.sample_comments(http, c)
            except Exception as e:  # extra detail only; never fail a search over it
                log.info("comments for %s failed: %s", c["id"], e)

    await asyncio.gather(*(one(c) for c in yt))
    n = sum(1 for c in yt if c.get("comment_sample"))
    _step(job, "comments", label, "done", f"comments sampled for {n} of {len(yt)} YouTube creators")


def _stopped(job: dict) -> None:
    """The user pressed Stop. Whatever was scored so far stays in the results."""
    job["status"] = "stopped"
    job["new"] = sum(1 for m in store.matches.get(job["company_id"], {}).values() if m.get("job_id") == job["id"])
    for s in job["steps"]:
        if s["status"] == "running":
            s.update(status="skipped", detail="stopped")


LINK_LOOKUPS = 20  # per search: the other platform of the best-ranked new creators


async def fetch_linked(creators: list[dict], limit: int = LINK_LOOKUPS) -> int:
    """Fetch the YouTube channel or TikTok profile that a creator links to, so the same person's numbers
    on both platforms end up in one row (the way Prenew tracks collaborations). Returns profiles added."""
    status = settings.source_status()
    have = _library_keys()
    want: dict[str, list[str]] = {"youtube": [], "tiktok": [], "twitch": []}
    for c in creators:
        for network, key in linking.missing_links(c, have):
            if status.get(network) and key not in have and sum(map(len, want.values())) < limit:
                want[network].append(linking.lookup_handle(key))
                have.add(key)
    if not any(want.values()):
        return 0
    label = LINKED_LABEL
    found = []
    async with httpx.AsyncClient() as http:
        for network, lookup in (("youtube", youtube.lookup_handles), ("tiktok", tiktok.lookup_handles),
                                ("twitch", twitch.lookup_logins)):
            if want[network]:
                try:
                    found += await lookup(http, want[network], label)
                except Exception as e:  # extra detail only; never fail a search over it
                    log.warning("linked %s lookup failed: %s", network, e)
    added = 0
    for c in found:
        if c["id"] in store.creators:
            continue
        metrics.compute(c)
        c["avatar"], c["cover"] = c.get("avatar_src"), c.get("cover_src")
        c["fetched_at"] = now_iso()
        store.creators[c["id"]] = c
        added += 1
    store.save()
    return added


def _library_keys() -> set[str]:
    return {k for c in store.creators.values() for k in linking.own_keys(c)}


async def _link_step(job: dict, company: dict) -> None:
    label = "Adding their other platforms"
    new = sorted((m["score"], cid) for cid, m in store.matches.get(company["id"], {}).items() if m.get("job_id") == job["id"])
    creators = [store.creators[cid] for _, cid in reversed(new) if cid in store.creators]
    have = _library_keys()
    if not any(linking.missing_links(c, have) for c in creators):
        return
    _step(job, "link", label)
    try:
        added = await fetch_linked(creators)
        _step(job, "link", label, "done", f"YouTube/TikTok numbers added for {added} creators" if added else "nothing new")
    except Exception as e:
        log.exception("linking profiles failed")
        _step(job, "link", label, "error", str(e)[:160])


MIN_MARKET_FIT = 35  # below this the creator's audience is clearly outside the chosen markets
AI_CHECK = {"local": 10, "cloud": 40}  # creators the AI re-checks per search; the rest keep their quick score


def check_limit(ai: dict) -> int:
    """How many creators the AI re-checks per search. Your own GPU server costs nothing per request: all of them."""
    if ai.get("self_hosted"):
        return config.MAX_SCORE_PER_JOB
    return AI_CHECK["local" if ai["local"] else "cloud"]


async def _plan(company: dict, search: dict, platforms: list[str], ai: dict) -> tuple[list[dict], str]:
    """Local-language search terms: remembered per search, else the AI writes them, else templates."""
    # v3: v2 plans for searches without a creator type aimed at the brand's product (gaming PCs); don't reuse them.
    key = json.dumps(["v3", sorted(search["markets"]), sorted(platforms), sorted(search.get("tags") or []),
                      (search.get("focus") or "").strip().lower()])
    cache = company.setdefault("plan_cache", {})
    if key in cache:
        return cache[key], "same as last time, no AI needed"
    if ai["ready"]:
        try:
            ai_plans = await asyncio.wait_for(llm.plan_searches(company, search, platforms), 240)
            # An answer without a single usable search isn't a plan: use the templates and ask again next time.
            if any(p[k] for p in ai_plans for k in ("youtube_queries", "tiktok_queries", "tiktok_hashtags")):
                plans = _blend(ai_plans, rules.template_plan(company, search, platforms))
                cache[key] = plans
                while len(cache) > 40:
                    cache.pop(next(iter(cache)))
                return plans, f"written by {ai['label']}"
            log.warning("AI plan had no usable searches, using templates")
        except Exception as e:
            log.warning("AI planning failed, using templates: %s", e)
    return rules.template_plan(company, search, platforms), "from templates"


def _blend(ai_plans: list[dict], templates: list[dict]) -> list[dict]:
    """The AI's local-language ideas plus the plain templates (creator type + local word), which always
    find something even when a small model's ideas are off."""
    by_market = {p["market"]: p for p in ai_plans}
    out = []
    for t in templates:
        a = by_market.get(t["market"], {})

        def mix(key, from_template, total):
            return list(dict.fromkeys(t[key][:from_template] + (a.get(key) or [])))[:total]

        out.append({"market": t["market"], "youtube_queries": mix("youtube_queries", 1, 4),
                    "tiktok_queries": mix("tiktok_queries", 2, 5), "tiktok_hashtags": mix("tiktok_hashtags", 1, 3)})
    return out


async def score_pool(job: dict, company: dict, pool: list[dict], ai: dict) -> None:
    """1. Rules give every creator a score at once (free). 2. The search AI re-checks the best ones."""
    company_matches = store.matches.setdefault(company["id"], {})
    outside, ranked = 0, []
    for c in pool:
        r = rules.quick_score(c, company, job)
        if r["market_fit"] < MIN_MARKET_FIT and not job.get("keep_all"):
            outside += 1
            continue
        company_matches[c["id"]] = build_match(c, r, job["id"], job["markets"], company)
        ranked.append(c)
    store.save()
    job["outside"] = job.get("outside", 0) + outside
    detail = f"{len(ranked)} creators ranked" + (f"; {outside} outside your markets" if outside else "")
    _step(job, "rules", "Quick scores (free, no AI)", "done", detail)
    ranked.sort(key=lambda c: -company_matches[c["id"]]["score"])
    job["new"] = len(ranked)
    job["unscored"] = [c["id"] for c in ranked]  # = not checked by the AI yet
    if not ai["ready"]:
        _step(job, "score", "AI check", "skipped", "no AI set up; quick scores only")
        return
    await ai_check(job, company, ranked[:check_limit(ai)], ai)


async def ai_check(job: dict, company: dict, creators: list[dict], ai: dict) -> None:
    """Let the search AI re-score creators (it reads their posts: niche fit, competitors, a summary).
    A failed batch keeps its quick scores and stays in job["unscored"] for "Check more with AI"."""
    job_id = job["id"]
    job["to_score"] = len(creators)
    job["scored"] = 0
    job.pop("score_error", None)
    label = f"AI check with {ai['label']}" + (" (on this computer)" if ai["local"] else "")
    _step(job, "score", label, detail=f"0 / {len(creators)}")
    company_matches = store.matches.setdefault(company["id"], {})
    # A laptop runs one local request at a time; Claude and your own GPU server handle parallel batches well;
    # free tiers need care.
    sem = asyncio.Semaphore(ai.get("concurrency") or (1 if ai["local"] else config.SCORE_CONCURRENCY if ai["kind"] == "anthropic" else 2))
    outside = 0

    async def check(batch):
        nonlocal outside
        async with sem:
            try:
                results = await llm.score_batch(company, job, batch, ai)
            except Exception as e:
                log.warning("AI check batch failed: %s", e)
                job["score_error"] = str(e)[:240]
                results = None
        for c in batch:
            r = (results or {}).get(c["id"])
            if r is None:
                continue
            if not c.get("language") and r.get("language"):
                c["language"] = str(r["language"])[:2].lower()
            old = company_matches.get(c["id"]) or {"job_id": job_id, "search_markets": job["markets"]}
            match = rebuild(old, c, company, merge_ai(rules.quick_score(c, company, job), r))
            if c["id"] in job["unscored"]:
                job["unscored"].remove(c["id"])
            if match["fit_parts"]["market"] < MIN_MARKET_FIT and not job.get("keep_all"):
                outside += 1
                company_matches.pop(c["id"], None)
                continue
            company_matches[c["id"]] = match
        job["scored"] += len(batch)
        _step(job, "score", label, detail=f"{job['scored']} / {len(creators)}")
        store.save()

    size = ai.get("batch_size", config.SCORE_BATCH_SIZE)
    await asyncio.gather(*(check(creators[i:i + size]) for i in range(0, len(creators), size)))
    job["new"] = sum(1 for m in company_matches.values() if m.get("job_id") == job_id)
    job["outside"] = job.get("outside", 0) + outside
    failed = sum(1 for c in creators if c["id"] in job["unscored"])
    checked = len(creators) - failed
    parts = [f"{checked} checked"]
    if outside:
        parts.append(f"{outside} judged outside your markets")
    override = llm.model_overrides.get(ai["provider"])
    if override:
        parts.append(f"used {override['model']} because {override['reason']}")
    if failed:
        parts.append(f"{failed} kept their quick score: {job.get('score_error') or ai['label'] + ' failed'}")
    _step(job, "score", label, "error" if failed and not checked else "done", "; ".join(parts))


async def retry_scoring(job_id: str) -> None:
    """"Check more with AI": the next creators of this search that only have a quick score."""
    job = store.jobs[job_id]
    company = store.companies[job["company_id"]]
    ai = settings.ai_config()
    matches = store.matches.get(company["id"], {})
    waiting = [store.creators[cid] for cid in job.get("unscored", []) if cid in store.creators and cid in matches]
    waiting.sort(key=lambda c: -matches[c["id"]]["score"])
    job["unscored"] = [c["id"] for c in waiting]
    job["status"] = "running"
    earlier = job.get("new", 0)
    try:
        await ai_check(job, company, waiting[:check_limit(ai)], ai)
        job["status"] = "done"
    except asyncio.CancelledError:
        _stopped(job)
    except Exception as e:
        log.exception("AI check of job %s failed", job_id)
        job["status"] = "error"
        job["error"] = str(e)[:300]
    finally:
        job["retried_from"] = earlier
        job["finished_at"] = now_iso()
        store.save()


def search_of(match: dict) -> dict:
    """The search that found this creator (its creator types and markets), for re-scoring later."""
    job = store.jobs.get(match.get("job_id") or "")
    if job:
        return job
    return {"markets": match.get("search_markets") or [], "tags": match.get("matched_tags") or []}


def upgrade_library() -> None:
    """Creators and matches saved by older versions: add the new audience metrics and re-score with the
    current model, keeping every AI judgement already made (no AI calls, no quota)."""
    changed = False
    for c in store.creators.values():
        if c.get("assessed_v") != audience.VERSION:
            metrics.compute_stats(c)
            audience.assess(c)
            changed = True
    stale = set()
    for company_id, matches in store.matches.items():
        company = store.companies.get(company_id)
        if not company:
            continue
        for cid, m in list(matches.items()):
            c = store.creators.get(cid)
            if not c:
                continue
            if "fit" in m:
                if m.get("v") != scoring.VERSION:
                    stale.add(company_id)
                continue
            quick = rules.quick_score(c, company, search_of(m))
            if m.get("ai_checked"):
                # Keep the AI's old judgement: niche fit became content fit; its reasons become evidence.
                old = {"content_fit": m.get("niche_fit"), "market_fit": m.get("market_fit"), "brand_safety": m.get("brand_safety"),
                       "summary": m.get("summary"), "niche": m.get("niche"), "games": m.get("games"), "tags": m.get("tags"),
                       "competitor_sponsor": m.get("competitor_sponsor"),
                       "evidence": [scoring.evidence_item("content", "+", w, src="ai") for w in m.get("why", [])]
                                   + [scoring.evidence_item("brand", "-", f, src="ai") for f in m.get("red_flags", [])]}
                quick = merge_ai(quick, old)
            matches[cid] = rebuild(m, c, company, quick)
            changed = True
    for company_id in stale:  # scored by an older model: recompute from the saved judgements
        rescore_company(store.companies[company_id])
    if changed:
        store.save()


def rescore_company(company: dict) -> None:
    """The brand profile changed (goal, budget...): recompute Fit/Quality/match from the stored parts."""
    for cid, m in store.matches.get(company["id"], {}).items():
        c = store.creators.get(cid)
        if not c or "fit_parts" not in m:
            continue
        if not m.get("ai_checked"):  # rules only: cheap to redo, and budget or competitors may have changed
            store.matches[company["id"]][cid] = rebuild(m, c, company, rules.quick_score(c, company, search_of(m)))
            continue
        p = m["fit_parts"]
        # Keep the AI's judgement, but refresh the facts read from data (budget, competitors, comments...).
        facts = [e for e in rules.quick_score(c, company, search_of(m))["evidence"] if e.get("fact")]
        evidence = [e for e in m.get("evidence") or [] if e.get("src") == "ai"] + facts
        r = {"content_fit": p["content"], "audience_fit": p["audience"], "market_fit": p["market"], "brand_fit": p["brand"],
             "readiness": p["readiness"], "brand_safety": m.get("brand_safety"), "competitor_sponsor": m.get("competitor_sponsor"),
             "evidence": evidence, "unproven": m.get("unproven") or {},
             "ai_checked": m.get("checked") if m.get("checked") == "deep" else m.get("ai_checked"),
             **{k: m.get(k) for k in ("language", "country", "summary", "niche", "games", "tags", "matched_tags",
                                      "verdict", "collab_idea", "audience_note")}}
        store.matches[company["id"]][cid] = rebuild(m, c, company, r)
    store.save()
