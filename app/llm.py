"""All AI calls: search planning, creator scoring, pitch drafting, tag suggestions, web scouting.

Works with Claude (Anthropic SDK) or any OpenAI-compatible API (OpenAI, Gemini, OpenRouter, Ollama, ...),
whichever is chosen in Settings. Every call asks for JSON that matches a schema.
"""
import asyncio
import json
import logging
import re

import anthropic
import httpx

from . import config, settings
from .markets import LANGUAGES, MARKETS, PLATFORMS

log = logging.getLogger("scout")

FALLBACK_BETA = "server-side-fallback-2026-07-01"

_claude_clients: dict[str, anthropic.AsyncAnthropic] = {}
_use_fallbacks = config.CLAUDE_FALLBACKS


class LLMError(Exception):
    pass


# --- Claude ----------------------------------------------------------------------------------

def _claude(ai: dict) -> anthropic.AsyncAnthropic:
    workspace = ai.get("workspace_id") or ""
    cache_key = f"{ai['api_key']}|{workspace}"
    if cache_key not in _claude_clients:
        # Organization-wide keys must say which workspace to bill/use; workspace keys don't need this.
        headers = {"anthropic-workspace-id": workspace} if workspace else None
        _claude_clients[cache_key] = anthropic.AsyncAnthropic(api_key=ai["api_key"], max_retries=3, default_headers=headers)
    return _claude_clients[cache_key]


WORKSPACE_HELP = ("This Claude key belongs to your whole organization, so it needs a workspace. Paste your "
                  "Workspace ID (starts with wrkspc_) in Settings → Claude, or create an API key inside a workspace.")


def _claude_bad_request(e: anthropic.BadRequestError) -> LLMError | None:
    if "workspace" in str(e).lower():
        return LLMError(WORKSPACE_HELP if "anthropic-workspace-id" in str(e)
                        else f"Claude workspace problem: {e.message}. Check the Workspace ID in Settings.")
    return None


async def _create(ai: dict, **kwargs):
    """Claude messages.create with server-side refusal fallbacks when the account supports them."""
    global _use_fallbacks
    try:
        if _use_fallbacks:
            try:
                return await _claude(ai).beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except anthropic.BadRequestError as e:
                if "fallback" not in str(e).lower():
                    raise
                _use_fallbacks = False  # not enabled for this account/model; continue without it
        return await _claude(ai).messages.create(**kwargs)
    except anthropic.BadRequestError as e:
        raise _claude_bad_request(e) or LLMError(f"Claude API error 400: {e.message}") from e
    except anthropic.AuthenticationError as e:
        raise LLMError("Claude rejected the API key. Check it in Settings.") from e
    except anthropic.NotFoundError as e:
        raise LLMError(f"Claude model '{ai['model']}' isn't available to this key. Pick another in Settings.") from e
    except anthropic.RateLimitError as e:
        raise LLMError("Claude rate limit reached. Wait a minute and try again.") from e
    except anthropic.APIConnectionError as e:
        raise LLMError("Can't reach the Claude API. Check the internet connection.") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e


async def _json_claude(ai, system, user, schema, effort, max_tokens) -> dict:
    resp = await _create(
        ai,
        model=ai["model"],
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    if resp.stop_reason == "refusal":
        raise LLMError("Claude declined this request")
    if resp.stop_reason == "max_tokens":
        raise LLMError("Claude's answer was cut off (max_tokens)")
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if text is None:
        raise LLMError("Claude returned no text")
    return json.loads(text)


# --- OpenAI-compatible (OpenAI, Gemini, OpenRouter, Ollama, ...) -------------------------------

FENCE_RE = re.compile(r"^`{3}(?:json)?\s*|\s*`{3}$")


def _parse_json(text: str) -> dict:
    """Parse a JSON object even if the model wrapped it in code fences or added a sentence."""
    text = FENCE_RE.sub("", (text or "").strip())
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in the reply")
        return json.loads(text[start:end + 1])


class QuotaError(LLMError):
    """The model's quota is used up (retrying soon won't help)."""


class BusyError(LLMError):
    """The provider is overloaded right now."""


RETRY_DELAY_RE = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')


def _quota_kind(r: httpx.Response) -> tuple[str, float | None]:
    """("daily" | "minute", suggested wait). Gemini puts the quota name and a retryDelay in the error details."""
    text = r.text
    m = RETRY_DELAY_RE.search(text)
    wait = float(m.group(1)) if m else None
    if not wait:
        try:
            wait = float(r.headers.get("retry-after", ""))
        except ValueError:
            wait = None
    return ("daily" if "PerDay" in text or "per day" in text.lower() else "minute"), wait


async def _post_with_retry(http: httpx.AsyncClient, url: str, headers: dict, body: dict,
                           patient: bool = True) -> httpx.Response:
    """Short, bounded retries. A used-up daily quota returns at once: waiting can't fix it, and every
    retry used to add ~20s to a search that was going to fail anyway. Not `patient` = another model
    is waiting as a fallback, so give up after one quick retry."""
    tries = 4 if patient else 2
    for attempt in range(tries):
        try:
            r = await http.post(url, headers=headers, json=body)
        except httpx.TimeoutException as e:
            raise LLMError("The AI took too long to answer") from e
        except httpx.ConnectError as e:
            raise LLMError(f"Can't connect to {url.rsplit('/chat', 1)[0]}. Check the address (and that Ollama is running, if you use it).") from e
        if r.status_code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
            return r
        if r.status_code == 429:
            kind, wait = _quota_kind(r)
            if kind == "daily" or (wait or 0) > 45:
                return r
            await asyncio.sleep(wait or 5 * (attempt + 1))
        else:
            await asyncio.sleep((2, 6, 12)[attempt])
    return r


def _error_detail(r: httpx.Response) -> str:
    try:
        err = r.json()
        err = err[0] if isinstance(err, list) else err
        inner = err.get("error")
        return str(inner.get("message") if isinstance(inner, dict) else inner or err)[:240]
    except Exception:
        return r.text[:240]


async def _json_openai(ai, system, user, schema, max_tokens, patient: bool = True) -> dict:
    url = ai["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if ai["api_key"]:
        headers["Authorization"] = f"Bearer {ai['api_key']}"
    if ai["provider"] == "openrouter":
        headers["X-Title"] = "Scout"
    hint = "\n\nReply with only a JSON object that matches this JSON Schema. No other text:\n" + json.dumps(schema)
    # Strict JSON-schema mode first; fall back for providers or models that don't support it.
    attempts = [
        (system, {"response_format": {"type": "json_schema", "json_schema": {"name": "result", "schema": schema, "strict": True}}}),
        (system + hint, {"response_format": {"type": "json_object"}}),
        (system + hint, {}),
    ]
    problem = ""
    async with httpx.AsyncClient(timeout=240) as http:
        for sys_text, extra in attempts:
            body = {
                "model": ai["model"],
                "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": user}],
                ai["max_tokens_param"]: min(max_tokens, ai["max_tokens"]),
                **extra,
            }
            r = await _post_with_retry(http, url, headers, body, patient)
            if r.status_code in (401, 403):
                raise LLMError(f"{ai['label']} rejected the API key. Check it in Settings.")
            if r.status_code == 429:
                kind, _ = _quota_kind(r)
                what = "daily free quota is used up" if kind == "daily" else "rate limit or quota was hit"
                raise QuotaError(f"{ai['label']} ({ai['model']}): {what}. {_error_detail(r)}")
            if r.status_code in (500, 502, 503, 504):
                raise BusyError(f"{ai['label']} ({ai['model']}) is overloaded right now: {_error_detail(r)}")
            if r.status_code == 404:
                # Usually a retired or misspelled model; the provider's own message says which.
                raise LLMError(f"{ai['label']} can't use model '{ai['model']}': {_error_detail(r)} "
                               f"Pick another model in Settings.")
            if r.status_code == 400:
                problem = _error_detail(r)
                if "api key" in problem.lower() or "api_key" in problem.lower():  # Gemini reports bad keys as 400
                    raise LLMError(f"{ai['label']} rejected the API key: {problem}")
                continue  # probably an unsupported JSON mode; try the simpler one
            if r.status_code >= 400:
                raise LLMError(f"{ai['label']} error {r.status_code}: {_error_detail(r)}")
            try:
                message = r.json()["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError):
                problem = "unexpected response format"
                continue
            if message.get("refusal"):
                raise LLMError(f"{ai['label']} declined this request")
            try:
                data = _parse_json(message.get("content") or "")
            except ValueError as e:
                problem = f"reply wasn't valid JSON ({e})"
                continue
            # Non-strict modes can drop fields; retry with the next mode rather than fail later.
            missing = [k for k in schema.get("required", []) if k not in data]
            if missing:
                problem = f"reply was missing {', '.join(missing)}"
                continue
            return data
    raise LLMError(f"{ai['label']} couldn't produce the answer: {problem}")


# provider -> model that replaced the configured one after quota/overload errors (until Settings change)
model_overrides: dict[str, dict] = {}


def active_model(ai: dict) -> str:
    return model_overrides.get(ai["provider"], {}).get("model") or ai["model"]


def clear_overrides() -> None:
    model_overrides.clear()


async def _json(system: str, user: str, schema: dict, effort: str = "medium", max_tokens: int = 16000,
                ai: dict | None = None) -> dict:
    ai = ai or settings.ai_config()
    if not ai["ready"]:
        raise LLMError("No AI is set up yet. Open Settings and add a key for the AI you want to use.")
    if ai["kind"] == "anthropic":
        return await _json_claude(ai, system, user, schema, effort, max_tokens)
    # Try the configured model (or the one that already replaced it), then lighter ones from the same provider.
    # Gemini quotas are per model, so a used-up quota on one model often leaves the next one working.
    chain = [ai["model"]] + ai.get("fallback_models", [])
    start = active_model(ai)
    chain = chain[chain.index(start):] if start in chain else chain
    error: LLMError | None = None
    first_error: LLMError | None = None
    for i, model in enumerate(chain):
        try:
            data = await _json_openai({**ai, "model": model}, system, user, schema, max_tokens,
                                      patient=i == len(chain) - 1)
        except (QuotaError, BusyError) as e:
            error, first_error = e, first_error or e
            log.warning("%s failed (%s); trying the next model", model, e)
            continue
        if model != ai["model"]:
            prev = model_overrides.get(ai["provider"])
            reason = prev["reason"] if prev else (
                f"{ai['model']} " + ("quota used up" if isinstance(first_error, QuotaError) else "overloaded"))
            model_overrides[ai["provider"]] = {"model": model, "reason": reason}
        return data
    raise error or LLMError(f"{ai['label']} couldn't answer")


async def test_ai(ai: dict) -> str:
    """Tiny round trip for the Settings 'Test' button. Tests exactly the chosen model (no fallback)."""
    args = ("You are a connectivity check.", 'Reply with {"ok": true, "model": "<your model name>"}.',
            _obj({"ok": BOOL, "model": STR}))
    if ai["kind"] == "anthropic":
        data = await _json(*args, effort="low", max_tokens=1000, ai=ai)
    else:
        data = await _json_openai(ai, *args, max_tokens=1000)
    if not data.get("ok"):
        raise LLMError("The AI answered, but not in the expected format")
    return f"Connected: {ai['label']} ({ai['model']}) answers in the right format"


# Preferred model families per provider, best first. The number in the name is the version,
# so the newest matching model wins. This keeps working when providers retire old models.
_PREFERRED = {
    "gemini": [r"^gemini-(\d+(?:\.\d+)?)-flash$", r"^gemini-(\d+(?:\.\d+)?)-flash-lite$", r"^gemini-(\d+(?:\.\d+)?)-pro$"],
    "openai": [r"^gpt-(\d+(?:\.\d+)?)-mini$", r"^gpt-(\d+(?:\.\d+)?)$"],
    "anthropic": [r"^claude-opus-(\d+(?:-\d+)?)$", r"^claude-sonnet-(\d+(?:-\d+)?)$"],
}


def recommend_model(provider: str, models: list[str], current: str) -> str:
    """Keep the current model if the key can use it; otherwise the newest model from a sensible family."""
    if current in models or not models:
        return current
    for pattern in _PREFERRED.get(provider, []):
        hits = []
        for name in models:
            m = re.match(pattern, name)
            if m:
                hits.append((tuple(int(x) for x in re.split(r"[.-]", m.group(1))), name))
        if hits:
            return max(hits)[1]
    return models[0]


async def list_models(ai: dict) -> list[str]:
    """Model names this key can use, for the Settings dropdown."""
    if ai["kind"] == "anthropic":
        if not ai["api_key"]:
            return []
        try:
            return [m.id async for m in _claude(ai).models.list(limit=100)]
        except anthropic.BadRequestError as e:
            raise _claude_bad_request(e) or LLMError(f"Couldn't list Claude models: {e.message}") from e
        except anthropic.AuthenticationError as e:
            raise LLMError("Claude rejected the API key. Check it in Settings.") from e
        except anthropic.APIError as e:
            raise LLMError(f"Couldn't list Claude models: {e}") from e
    headers = {"Authorization": f"Bearer {ai['api_key']}"} if ai["api_key"] else {}
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.get(ai["base_url"].rstrip("/") + "/models", headers=headers)
    except httpx.HTTPError as e:
        raise LLMError(f"Can't reach {ai['base_url']}") from e
    if r.status_code >= 400:
        raise LLMError(f"{ai['label']} error {r.status_code}: {_error_detail(r)}")
    ids = [m.get("id", "") for m in r.json().get("data", [])]
    skip = ("embed", "tts", "whisper", "dall-e", "moderation", "image", "audio", "realtime", "transcribe", "search")
    return sorted({i.removeprefix("models/") for i in ids if i and not any(s in i.lower() for s in skip)})


def _obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
STR_LIST = {"type": "array", "items": STR}


def brand_block(company: dict, search: dict) -> str:
    """The company (from its profile) plus what this particular search asks for (from the search area)."""
    markets = ", ".join(f"{MARKETS[m]['name']} ({m})" for m in search.get("markets", []) if m in MARKETS)
    fmax = search.get("follower_max")
    lines = [
        "<brand>",
        f"Name: {company.get('name', '')}",
        f"About: {company.get('description') or 'n/a'}",
        "</brand>",
        "<search>",
        f"Creator types wanted: {', '.join(search.get('tags', [])) or 'not specified; infer what would sell this brand'}",
        f"Extra focus: {search.get('focus') or 'none'}",
        f"Target markets: {markets or 'n/a'}",
        f"Follower range: {search.get('follower_min') or 0:,} to {f'{fmax:,}' if fmax else 'any'}",
        f"Collaboration types offered: {', '.join(search.get('deal_types', [])) or 'open'}",
        f"Avoid: {', '.join(search.get('avoid', [])) or 'nothing specified'}",
    ]
    if search.get("example_creators"):
        lines.append(f"Example creators they like: {', '.join(search['example_creators'])}")
    lines.append("</search>")
    return "\n".join(lines)


# --- Search planning -------------------------------------------------------------------------

PLAN_SYSTEM = """You plan social media searches that surface small, niche creators for a brand's influencer program.

For each market, write searches the way local creators actually title and tag their own content: local language first (including slang and common local words), plus at most one English search when that niche is commonly discussed in English there. Make every search unmistakably local, because platform search is global: use words that only speakers of that language would write, and where natural add a local anchor (the country or a city in the local language, a local shop, prices in the local currency). A game or product name on its own returns creators from everywhere. Prefer specific sub-niches over broad terms, because broad terms only return huge accounts and brands. Never include the names of famous creators or of the brand itself.

Hashtags: lowercase, no '#', no spaces. Return empty lists for platforms that are not requested."""

PLAN_SCHEMA = _obj({
    "markets": {"type": "array", "items": _obj({
        "market": STR,
        "youtube_queries": STR_LIST,
        "tiktok_queries": STR_LIST,
        "tiktok_hashtags": STR_LIST,
        "instagram_hashtags": STR_LIST,
    })},
})


async def plan_searches(company: dict, search: dict, platforms: list[str]) -> list[dict]:
    markets = search["markets"]
    market_lines = "\n".join(
        f"- {m}: {MARKETS[m]['name']}, languages: {', '.join(LANGUAGES[l] for l in MARKETS[m]['languages'])}"
        for m in markets if m in MARKETS
    )
    wanted = []
    if "youtube" in platforms:
        wanted.append("youtube_queries: 4 video search queries")
    if "tiktok" in platforms:
        wanted.append("tiktok_queries: 2 search queries; tiktok_hashtags: 2 hashtags")
    if "instagram" in platforms:
        wanted.append("instagram_hashtags: 3 hashtags")
    user = (
        f"{brand_block(company, search)}\n\n"
        f"Markets:\n{market_lines}\n\n"
        f"Per market, return: {'; '.join(wanted)}. Cover the different creator types wanted rather than repeating one."
    )
    data = await _json(PLAN_SYSTEM, user, PLAN_SCHEMA)
    keys = ("youtube_queries", "tiktok_queries", "tiktok_hashtags", "instagram_hashtags")
    plans = []
    for m in data["markets"]:
        if isinstance(m, dict) and m.get("market") in markets:
            # Keep only non-empty strings, so a sloppy reply can't break the scrapers.
            plans.append({"market": m["market"], **{k: [str(q).strip().lstrip("#") for q in m.get(k) or [] if str(q).strip()] for k in keys}})
    return plans


# --- Scoring ---------------------------------------------------------------------------------

SCORE_SYSTEM = """You are an influencer-discovery analyst for a marketing team. You judge whether social media creators are a good partnership fit for one specific brand. You are skeptical of vanity metrics and you value small creators whose audiences are genuinely engaged and relevant.

Score each creator from 0 to 100 on:
- niche_fit: how closely their actual recent content matches the creator types and focus in the search (or, if none are given, creators whose audience would buy from this brand). 90+ = core niche, posts about it regularly. 60-80 = adjacent audience that would plausibly buy. Below 40 = unrelated.
- market_fit: how likely their audience is in the search's target markets, judged from the language of their posts, stated location and platform country. 90+ = clearly local to a target market. 50 = unclear or mixed. Below 30 = clearly elsewhere.
- brand_safety: 100 = nothing concerning. Subtract for gambling or skin betting, hate, adult content, misinformation, or heavy controversy.

Also return for each creator:
- language: ISO 639-1 code of the language they mostly post in.
- country: ISO 3166-1 alpha-2 code of where they appear to be based, or "" if unknown.
- summary: one sentence of at most 110 characters that a marketer can read at a glance: who they are and why they matter for this brand.
- niche: their main content category in 1-3 words, for example "Gaming", "Tech reviews", "PC building", "Setups & desks", "Esports".
- games: the specific games they mainly play or cover, as titles (for example "Valorant", "Counter-Strike 2", "Minecraft"). Empty list if they don't focus on particular games.
- tags: 3 to 5 short content tags (1-3 words, Title Case), most specific first.
- matched_tags: which of the search's "creator types wanted" this creator genuinely fits, copied exactly as written there. Empty list if none, or if no creator types were given.
- why: 2 or 3 short reasons, each tied to evidence in their content or stats.
- red_flags: short concerns (competitor sponsorship, off-niche, inactive, signs of bought followers, unsafe content). Empty list if none.
- competitor_sponsor: true only if they appear to be sponsored by a direct competitor of the brand.

Judge only from the data provided and do not invent facts. Write summary, tags, why and red_flags in English. Return one result per creator, using the creator's id."""

SCORE_SCHEMA = _obj({
    "results": {"type": "array", "items": _obj({
        "id": STR,
        "niche_fit": INT,
        "market_fit": INT,
        "brand_safety": INT,
        "language": STR,
        "country": STR,
        "summary": STR,
        "niche": STR,
        "games": STR_LIST,
        "tags": STR_LIST,
        "matched_tags": STR_LIST,
        "why": STR_LIST,
        "red_flags": STR_LIST,
        "competitor_sponsor": BOOL,
    })},
})


def _compact(c: dict) -> dict:
    er = c.get("engagement_rate")
    return {
        "id": c["id"],
        "platform": PLATFORMS[c["platform"]],
        "name": c.get("name"),
        "handle": c.get("handle"),
        "followers": c.get("followers"),
        "bio": (c.get("bio") or "")[:600],
        "category": c.get("category"),
        "stated_country": c.get("country") or None,
        "stated_language": c.get("language") or None,
        "avg_views": c.get("avg_views"),
        "avg_views_window": c.get("views_window"),
        "views_trend_pct": round(c["views_trend"] * 100) if c.get("views_trend") is not None else None,
        "engagement_rate_pct": round(er * 100, 2) if er is not None else None,
        "engagement_vs_typical_for_size": c.get("engagement_vs_typical"),
        "posts_per_month": c.get("posts_per_month"),
        "days_since_last_post": c.get("days_since_last_post"),
        "recent_posts": [
            {"text": (p.get("title") or "")[:150], "views": p.get("views"), "likes": p.get("likes"),
             "comments": p.get("comments"), **({"short": True} if p.get("is_short") else {})}
            for p in c.get("recent_posts", [])[:10]  # enough titles to tell which games they play
        ],
    }


async def score_batch(company: dict, search: dict, creators: list[dict]) -> dict[str, dict]:
    system = SCORE_SYSTEM + "\n\n" + brand_block(company, search)
    user = "Creators to evaluate:\n" + json.dumps([_compact(c) for c in creators], ensure_ascii=False)
    data = await _json(system, user, SCORE_SCHEMA)
    defaults = {"niche_fit": 0, "market_fit": 50, "brand_safety": 100, "language": "", "country": "", "summary": "",
                "niche": "", "games": [],
                "tags": [], "matched_tags": [], "why": [], "red_flags": [], "competitor_sponsor": False}
    return {r["id"]: {**defaults, **r} for r in data["results"] if isinstance(r, dict) and r.get("id")}


# --- Outreach --------------------------------------------------------------------------------

PITCH_SYSTEM = """You write first-contact outreach messages from a brand to a social media creator.

Keep it short (90 to 140 words), warm and specific, with no hype and at most one emoji. Mention one or two concrete pieces of their recent content by topic. State one clear collaboration idea using the brand's collaboration types, and end with a simple question. Write the message in the creator's own language, and sign it as "<brand name> team". Also give a short email subject line and an English translation of the message."""

PITCH_SCHEMA = _obj({"language": STR, "subject": STR, "message": STR, "english": STR})


async def draft_pitch(company: dict, search: dict, creator: dict, match: dict) -> dict:
    lang = match.get("language") or creator.get("language") or "en"
    user = (
        f"{brand_block(company, search)}\n\n"
        f"Creator (write in {LANGUAGES.get(lang, lang)}):\n"
        + json.dumps(_compact(creator), ensure_ascii=False)
        + f"\n\nWhy they fit: {'; '.join(match.get('why', []))}"
    )
    return await _json(PITCH_SYSTEM, user, PITCH_SCHEMA)


# --- Company setup helper --------------------------------------------------------------------

TAGS_SYSTEM = """You help a marketing team decide which social media creators to partner with. Given a company description, suggest 10 short creator types (1-3 words, Sentence case), meaning content niches whose audiences would buy from this company. Mix obvious core niches with a few adjacent, less obvious ones where small creators are easier to find. Don't repeat any of the types the team already has."""


async def suggest_tags(name: str, description: str, existing: list[str]) -> list[str]:
    user = f"Company: {name}\nAbout: {description or 'n/a'}\nAlready have: {', '.join(existing) or 'none'}"
    data = await _json(TAGS_SYSTEM, user, _obj({"tags": STR_LIST}), effort="low", max_tokens=2000)
    have = {t.lower() for t in existing}
    return [t.strip() for t in data["tags"] if isinstance(t, str) and t.strip() and t.lower() not in have][:10]


# --- Suggested searches (for people who don't know what to search for) ------------------------

SEARCHES_SYSTEM = """You help a marketing team that doesn't know where to start with influencer marketing. Suggest ready-to-run searches for social media creators who would suit their company.

For each search give:
- title: at most 6 words, concrete (who and where), e.g. "Budget PC builders in Finland".
- description: one sentence (at most 20 words) saying who it finds and why they suit this company.
- query: an optional 1-3 word search phrase (a game, product or topic), or "".
- tags: 1-3 creator types (1-3 words each, Sentence case).
- markets: 1-3 target countries as ISO codes from the allowed list.
- platforms: 1-3 of youtube, tiktok, instagram.
- follower_min and follower_max: the follower range; follower_max 0 means no upper limit.

Make the searches varied: different niches, markets, platforms and sizes. Include at least one for small creators (under 10k followers) and one for mid-size creators (50k-250k)."""

SEARCHES_SCHEMA = _obj({
    "searches": {"type": "array", "items": _obj({
        "title": STR,
        "description": STR,
        "query": STR,
        "tags": STR_LIST,
        "markets": STR_LIST,
        "platforms": STR_LIST,
        "follower_min": INT,
        "follower_max": INT,
    })},
})


def _clean_search(s: dict) -> dict | None:
    markets = [m for m in (s.get("markets") or []) if m in MARKETS][:3]
    platforms = [p for p in (s.get("platforms") or []) if p in PLATFORMS]
    if not s.get("title") or not markets:
        return None
    try:
        fmin = max(0, int(s.get("follower_min") or 0))
        fmax = int(s.get("follower_max") or 0) or None
    except (TypeError, ValueError):
        fmin, fmax = 1000, None
    if fmax is not None and fmax <= fmin:
        fmax = None
    return {
        "title": str(s["title"])[:60],
        "description": str(s.get("description") or "")[:160],
        "query": str(s.get("query") or "")[:40],
        "tags": [str(t)[:30] for t in (s.get("tags") or []) if t][:3],
        "markets": markets,
        "platforms": platforms or list(PLATFORMS),
        "follower_min": fmin,
        "follower_max": fmax,
    }


async def suggest_searches(company: dict, count: int = 6, avoid_titles: list[str] | None = None) -> list[dict]:
    allowed = ", ".join(f"{code} ({m['name']})" for code, m in MARKETS.items())
    user = (
        f"Company: {company.get('name', '')}\nAbout: {company.get('description') or 'n/a'}\n"
        f"Creator types they may like: {', '.join(company.get('suggested_tags', [])) or 'n/a'}\n"
        f"Markets they already search: {', '.join(company.get('search', {}).get('markets', [])) or 'none yet'}\n"
        f"Allowed market codes: {allowed}\n"
        f"Already suggested (don't repeat): {'; '.join(avoid_titles or []) or 'none'}\n\n"
        f"Suggest {count} searches."
    )
    data = await _json(SEARCHES_SYSTEM, user, SEARCHES_SCHEMA, effort="low", max_tokens=4000)
    return [c for c in (_clean_search(s) for s in data["searches"] if isinstance(s, dict)) if c][:count]


# --- AI web scout ----------------------------------------------------------------------------

SCOUT_TOOL = {
    "name": "report_creators",
    "description": "Report the creators you found. Call this exactly once, at the end of your research.",
    "strict": True,
    "input_schema": _obj({
        "creators": {"type": "array", "items": _obj({
            "platform": {"type": "string", "enum": list(PLATFORMS)},
            "handle": STR,
            "evidence": STR,
        })},
    }),
}

HANDLE_RE = {
    "youtube": re.compile(r"youtube\.com/@([\w.\-]+)", re.I),
    "tiktok": re.compile(r"tiktok\.com/@([\w.\-]+)", re.I),
    "instagram": re.compile(r"instagram\.com/([\w.]+)", re.I),
}


def _clean_handle(platform: str, raw: str) -> str | None:
    raw = (raw or "").strip()
    m = HANDLE_RE[platform].search(raw)
    handle = m.group(1) if m else raw.lstrip("@").split("/")[0]
    return handle if re.fullmatch(r"[\w.\-]{2,40}", handle) else None


async def web_scout(company: dict, search: dict, market: str, platforms: list[str], limit: int = 12) -> list[dict]:
    """Let Claude search the open web (lists, forums, local press) for small creators hashtag search misses.

    Claude only: it relies on Anthropic's server-side web search tool.
    """
    ai = settings.ai_config()
    if not ai["web_search"] or not ai["ready"]:
        raise LLMError("The AI web scout needs Claude as the AI in Settings")
    names = ", ".join(PLATFORMS[p] for p in platforms)
    prompt = (
        f"{brand_block(company, search)}\n\n"
        f"Find up to {limit} real creators on {names} who are based in {MARKETS[market]['name']} "
        f"and match the search above.\n"
        f"Stay inside the follower range. Prioritise small and mid-sized creators that big influencer databases miss: "
        f"look at local creator lists, forum and Reddit recommendations, local press, event line-ups and "
        f"collaborations between creators. Only report accounts you saw evidence for, with their exact handle. "
        f"When you are done, call report_creators once."
    )
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}, SCOUT_TOOL]
    messages = [{"role": "user", "content": prompt}]
    for _ in range(4):
        resp = await _create(
            ai, model=ai["model"], max_tokens=16000, tools=tools, messages=messages,
            output_config={"effort": "medium"},
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == "report_creators":
                found = []
                for c in block.input.get("creators", []):
                    if c.get("platform") in platforms:
                        handle = _clean_handle(c["platform"], c.get("handle", ""))
                        if handle:
                            found.append({"platform": c["platform"], "handle": handle, "evidence": c.get("evidence", "")})
                return found
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "pause_turn":
            continue  # server-side search loop paused; resume it
        if resp.stop_reason == "end_turn":
            messages.append({"role": "user", "content": "Now call report_creators with the creators you found."})
            continue
        break
    return []
