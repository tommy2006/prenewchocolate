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

from . import config, partners, settings
from .store import store
from .markets import LANGUAGES, MARKETS, PLATFORMS, SEARCH_PLATFORMS

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
    async with httpx.AsyncClient(timeout=ai.get("timeout", 240)) as http:
        for sys_text, extra in attempts:
            body = {
                "model": ai["model"],
                "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": user}],
                ai["max_tokens_param"]: min(max_tokens, ai["max_tokens"]),
                **({"temperature": ai["temperature"]} if ai.get("temperature") is not None else {}),
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


# --- Local models (Ollama's own API) ----------------------------------------------------------

def ollama_base(ai: dict) -> str:
    return (ai.get("base_url") or "http://localhost:11434").rstrip("/").removesuffix("/v1")


async def _json_ollama(ai, system, user, schema, max_tokens) -> dict:
    """Ollama's native chat API: `format` constrains the output to the JSON schema (no parsing surprises)
    and `think: false` skips the long hidden reasoning some small models do by default."""
    body = {
        "model": ai["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False,
        "format": schema,
        "think": False,
        "keep_alive": "30m",  # stay loaded between batches; loading takes longer than answering
        "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": min(max_tokens, ai["max_tokens"])},
    }
    url = ollama_base(ai) + "/api/chat"
    async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=5)) as http:
        for _ in range(2):
            try:
                r = await http.post(url, json=body)
            except httpx.ConnectError as e:
                raise LLMError("The local AI isn't running. Start the Ollama app (or press Start in Settings → Local AI).") from e
            except httpx.TimeoutException as e:
                raise LLMError("The local AI took too long to answer") from e
            if r.status_code == 400 and "think" in r.text.lower() and "think" in body:
                body.pop("think")  # this model has no thinking switch
                continue
            break
    if r.status_code == 404:
        raise LLMError(f"The local model '{ai['model']}' isn't downloaded yet. Open Settings → Local AI and press Download.")
    if r.status_code >= 400:
        raise LLMError(f"Local AI error {r.status_code}: {_error_detail(r)}")
    try:
        data = _parse_json(r.json()["message"]["content"])
    except (ValueError, KeyError, TypeError) as e:
        raise LLMError(f"The local AI's answer wasn't valid JSON ({e})") from e
    missing = [k for k in schema.get("required", []) if k not in data]
    if missing:
        raise LLMError(f"The local AI's answer was missing {', '.join(missing)}")
    return data


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
    if ai["kind"] == "ollama":
        return await _json_ollama(ai, system, user, schema, max_tokens)
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
    elif ai["kind"] == "ollama":
        data = await _json_ollama(ai, *args, max_tokens=200)
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
    if ai["kind"] == "ollama":
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                r = await http.get(ollama_base(ai) + "/api/tags")
        except httpx.HTTPError as e:
            raise LLMError("The local AI (Ollama) isn't running. Start the Ollama app.") from e
        return sorted(m["name"] for m in r.json().get("models", []) if "embed" not in m["name"])
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


GOAL_TEXT = {
    "sales": "Sales: creators whose viewers will actually buy. Audience fit matters most.",
    "balanced": "Balanced: sales and reach both matter.",
    "awareness": "Awareness: reach many relevant people in the target markets.",
}


def brand_block(company: dict, search: dict, past_limit: int = 30) -> str:
    """The company (profile), what this search asks for, what worked before and what the team rejected."""
    markets = ", ".join(f"{MARKETS[m]['name']} ({m})" for m in search.get("markets", []) if m in MARKETS)
    fmax = search.get("follower_max")
    p = company.get("profile") or {}
    lines = ["<brand>", f"Name: {company.get('name', '')}", f"About: {company.get('description') or 'n/a'}"]
    for label, value in (("Target customer", p.get("target_customer")), ("Price range", p.get("price_range")),
                         ("Values and tone", p.get("values")), ("Website", p.get("website"))):
        if value:
            lines.append(f"{label}: {value}")
    if p.get("min_audience_age"):
        lines.append(f"Audience must mostly be {p['min_audience_age']}+ (younger audiences can't buy)")
    if p.get("competitors"):
        lines.append(f"Competitors (a creator sponsored by one is not a partner): {', '.join(p['competitors'])}")
    if p.get("no_go"):
        lines.append(f"Never work with: {', '.join(p['no_go'])}")
    if p.get("budget_max"):
        lines.append(f"Budget per collaboration: up to EUR {p['budget_max']:,}")
    lines.append(f"Campaign goal: {GOAL_TEXT.get(p.get('goal') or 'balanced', GOAL_TEXT['balanced'])}")
    lines += [
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
    past = partners.brief(company, limit=past_limit)
    if past:
        lines += [
            "<past_collaborations>",
            "Creators this brand has already worked with. Treat them as examples of what fits "
            "(niches, sizes, markets, platforms); the goal is new creators like them.",
            past,
            "</past_collaborations>",
        ]
    feedback = team_feedback(company)
    if feedback:
        lines += ["<team_feedback>", "How the marketing team judged earlier suggestions. Learn from it.", feedback, "</team_feedback>"]
    return "\n".join(lines)


def team_feedback(company: dict, limit: int = 12) -> str:
    """Creators the team shortlisted or rejected (with the reason they gave), newest first."""
    rows = []
    for cid, m in store.matches.get(company.get("id"), {}).items():
        c = store.creators.get(cid)
        if not c or not m.get("status"):
            continue
        size = f"{c.get('followers') or 0:,} followers"
        what = ", ".join(x for x in (PLATFORMS.get(c["platform"]), m.get("niche"), size, m.get("country")) if x)
        if m["status"] == "hidden":
            rows.append((m.get("status_at") or "", f"Rejected {c.get('name')} ({what})" + (f": {m['feedback']}" if m.get("feedback") else "")))
        else:
            rows.append((m.get("status_at") or "", f"Shortlisted {c.get('name')} ({what})"))
    rows.sort(reverse=True)
    return "\n".join(r for _, r in rows[:limit])


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
        # These go through web search ("site:tiktok.com fortnite suomi"): short phrases find the most accounts.
        wanted.append("tiktok_queries: 4 short phrases of 2-3 words, each a game or topic plus one local-language "
                      "word (e.g. 'fortnite suomi', 'minecraft pelaaja'); tiktok_hashtags: 2 hashtags")
    user = (
        f"{brand_block(company, search)}\n\n"
        f"Markets:\n{market_lines}\n\n"
        f"Per market, return: {'; '.join(wanted)}. Cover the different creator types wanted rather than repeating one."
    )
    data = await _json(PLAN_SYSTEM, user, PLAN_SCHEMA)
    keys = ("youtube_queries", "tiktok_queries", "tiktok_hashtags")
    plans = []
    for m in data["markets"]:
        if isinstance(m, dict) and m.get("market") in markets:
            # Keep only non-empty strings, so a sloppy reply can't break the scrapers.
            plans.append({"market": m["market"], **{k: [str(q).strip().lstrip("#") for q in m.get(k) or [] if str(q).strip()] for k in keys}})
    return plans


# --- Scoring ---------------------------------------------------------------------------------

DIMS = ["content", "audience", "market", "brand", "readiness"]

SCORE_SYSTEM = """You are an influencer-marketing analyst. You judge, the way an experienced human marketer would, whether each creator is a good partner for one specific brand. Look past follower counts: who actually watches, whether those people would buy, and whether a sponsored post would feel natural. You value small creators whose audiences are genuinely engaged and relevant.

Score each creator from 0 to 100 on:
- content_fit: how closely their actual recent content matches the creator types and focus in the search (or, if none are given, what would sell this brand). 90+ = core niche, posts about it regularly. 60-80 = adjacent. Below 40 = unrelated.
- audience_fit: how likely their viewers are the brand's customers: age (respect the brand's minimum audience age), interest in what the brand sells, buying power, trust in the creator (do viewers ask them for advice?).
- market_fit: how likely their audience is in the target markets, from post language, comment language, stated location and platform country. 90+ = clearly local. 50 = unclear. Below 30 = elsewhere.
- brand_fit: whether their tone and values suit the brand and would make its message believable. Lower it for anything on the brand's "never work with" list.
- readiness: how ready they are for a collaboration: contact details, experience with sponsored posts or codes (but not so many ads that viewers tune out), posting regularly, a format where a sponsored segment fits naturally, and a likely price within the brand's budget.
- brand_safety: 100 = nothing concerning. Subtract for gambling or skin betting, hate, adult content, misinformation, or heavy controversy.
Use the whole range. Most real creators have some weakness: reserve 90+ for strong evidence you can cite, and give 100 only when there is truly nothing to improve.

Also return:
- language: ISO 639-1 code of the language they mostly post in. country: ISO 3166-1 alpha-2 code of where they are based, or "".
- summary: one sentence of at most 110 characters a marketer can read at a glance: who they are and why they matter for this brand.
- niche: their main content category in 1-3 words. games: titles of the games they mainly cover (empty if none).
- tags: 3 to 5 short content tags (Title Case), most specific first.
- matched_tags: which of the search's "creator types wanted" they genuinely fit, copied exactly. Empty if none.
- evidence: 3 to 6 claims behind your scores. Each has dim (one of content, audience, market, brand, readiness), sign ("+" helps the fit, "-" hurts it), claim (one short sentence in English), and posts: the refs of the posts that show it (e.g. ["p1", "p4"]), plus comments: refs of comments that show it (e.g. ["c2"]). Cite only refs that appear in the data. Every claim about content, audience or brand must cite at least one post or comment.
- competitor_sponsor: true only if they appear sponsored by one of the brand's competitors, or are themselves a shop selling the same products.

Judge only from the data provided and never invent facts. Return one result per creator, using the creator's id."""

EVIDENCE = {"type": "array", "items": _obj({
    "dim": {"type": "string", "enum": DIMS},
    "sign": {"type": "string", "enum": ["+", "-"]},
    "claim": STR,
    "posts": STR_LIST,
    "comments": STR_LIST,
})}

SCORE_SCHEMA = _obj({
    "results": {"type": "array", "items": _obj({
        "id": STR,
        "content_fit": INT,
        "audience_fit": INT,
        "market_fit": INT,
        "brand_fit": INT,
        "readiness": INT,
        "brand_safety": INT,
        "language": STR,
        "country": STR,
        "summary": STR,
        "niche": STR,
        "games": STR_LIST,
        "tags": STR_LIST,
        "matched_tags": STR_LIST,
        "evidence": EVIDENCE,
        "competitor_sponsor": BOOL,
    })},
})


def _audience_facts(c: dict) -> dict:
    a, auth, sp = c.get("audience") or {}, c.get("authenticity") or {}, c.get("sponsorship") or {}
    return {
        "comment_languages": a.get("languages") or None,
        "generic_comment_share": a.get("generic_share"),
        "question_share": a.get("question_share"),
        "authenticity_signals": [x["text"] for x in auth.get("signals", [])] or None,
        "sponsored_posts": f"{sp.get('sponsored', 0)} of {sp.get('checked', 0)}" if sp.get("checked") else None,
        "posts_with_discount_codes": sp.get("with_codes") or None,
        "has_email": bool(c.get("emails")),
        "estimated_price_eur": f"{c['price']['low']}-{c['price']['high']}" if c.get("price") else None,
    }


def _compact(c: dict, lite: bool = False, n_posts: int | None = None, n_comments: int = 8, desc_len: int = 0) -> dict:
    """What the AI sees about a creator. Posts and comments carry refs (p1, c1) that evidence must cite.
    `lite` (local models) sends fewer, shorter posts: on a laptop CPU every input token costs time."""
    er = c.get("engagement_rate")
    n, text_len, bio_len = (6, 90, 300) if lite else (10, 150, 600)
    n = n_posts or n
    return {
        "id": c["id"],
        "platform": PLATFORMS[c["platform"]],
        "name": c.get("name"),
        "handle": c.get("handle"),
        "followers": c.get("followers"),
        "bio": (c.get("bio") or "")[:bio_len],
        "stated_country": c.get("country") or None,
        "stated_language": c.get("language") or None,
        "median_views": c.get("median_views"),
        "avg_views_window": c.get("views_window"),
        "views_trend_pct": round(c["views_trend"] * 100) if c.get("views_trend") is not None else None,
        "engagement_rate_pct": round(er * 100, 2) if er is not None else None,
        "engagement_vs_typical_for_size": c.get("engagement_vs_typical"),
        "posts_per_month": c.get("posts_per_month"),
        "days_since_last_post": c.get("days_since_last_post"),
        **({} if lite else _audience_facts(c)),
        "recent_posts": [
            {"ref": f"p{i + 1}", "text": (p.get("title") or "")[:text_len],
             **({"description": p["desc"][:desc_len]} if desc_len and p.get("desc") else {}),
             "views": p.get("views"), "likes": p.get("likes"), "comments": p.get("comments"),
             **({"short": True} if p.get("is_short") else {})}
            for i, p in enumerate(c.get("recent_posts", [])[:n])
        ],
        **({"sample_comments": [{"ref": f"c{i + 1}", "text": x["text"][:140]}
                                for i, x in enumerate(c.get("comment_sample", [])[:n_comments])]}
           if n_comments and not lite and c.get("comment_sample") else {}),
    }


REF_RE = re.compile(r"\[?\b([pc])(\d{1,2})\b\]?", re.I)


def _resolve(c: dict, dim: str, sign: str, claim: str, post_refs: list, comment_refs: list, src: str) -> dict | None:
    """Turn cited refs into real posts and comments. A claim that cites only refs that don't exist was
    probably invented, so it's dropped."""
    posts, quotes, cited, bad = [], [], 0, 0
    recent, comments = c.get("recent_posts", []), c.get("comment_sample", [])
    for ref in post_refs or []:
        m = REF_RE.fullmatch(str(ref).strip())
        i = int(m.group(2)) - 1 if m and m.group(1).lower() == "p" else -1
        if 0 <= i < min(len(recent), 12):
            cited += 1
            posts.append({"title": (recent[i].get("title") or "")[:100], "url": recent[i].get("url")})
        else:
            bad += 1
    for ref in comment_refs or []:
        m = REF_RE.fullmatch(str(ref).strip())
        i = int(m.group(2)) - 1 if m and m.group(1).lower() == "c" else -1
        if 0 <= i < min(len(comments), 30):
            cited += 1
            quotes.append(comments[i]["text"][:160])
        else:
            bad += 1
    if bad and not cited:
        return None
    claim = REF_RE.sub("", claim or "").replace("()", "").strip(" ,;")
    if not claim or dim not in DIMS:
        return None
    return {"dim": dim, "sign": "-" if sign == "-" else "+", "text": claim[:200], "posts": posts[:3], "quotes": quotes[:2],
            "src": src, "fact": False}


def _evidence(c: dict, items: list, src: str) -> list[dict]:
    out = []
    for e in items or []:
        if isinstance(e, dict):
            r = _resolve(c, e.get("dim"), e.get("sign"), e.get("claim") or "", e.get("posts"), e.get("comments"), src)
            if r:
                out.append(r)
    return out


# Local models on a laptop CPU write ~5 tokens a second, so they answer only what the rules can't know
# (fit, audience, safety, competitors, a summary) and read only titles and bio. Stats and facts come from rules.
LOCAL_SCORE_SYSTEM = """You judge whether social media creators fit one brand's influencer program. For each creator, from their bio and post titles only:
- content_fit 0-100: how well their content matches the creator types wanted (90+ core niche, 60-80 adjacent, under 40 unrelated).
- audience_fit 0-100: how likely their viewers are the brand's customers (old enough to buy, interested in what the brand sells).
- market_fit 0-100: how likely their audience is in the target markets, from the language of their posts and their country (90+ clearly local, 50 unclear, under 30 elsewhere).
- brand_safety 0-100: 100 unless gambling, skin betting, adult content, hate or big controversy.
- niche: 1-3 words. games: titles of the games they mainly cover (can be empty).
- summary: at most 90 characters, in English: who they are and why they matter (or don't) for this brand.
- why: 1 or 2 short reasons in English, each ending with the posts that show it, e.g. "Builds budget gaming PCs [p1, p3]". Use "-" at the start for a reason against.
- competitor_sponsor: true if the account IS a company selling the same kind of products as the brand, or is sponsored by one. Such accounts are competitors, not partners: give them content_fit under 30.
Judge only from the data given."""

LOCAL_SCORE_SCHEMA = _obj({
    "results": {"type": "array", "items": _obj({
        "id": STR,
        "content_fit": INT,
        "audience_fit": INT,
        "market_fit": INT,
        "brand_safety": INT,
        "niche": STR,
        "games": STR_LIST,
        "summary": STR,
        "why": STR_LIST,
        "competitor_sponsor": BOOL,
    })},
})


def _compact_local(c: dict) -> dict:
    return {
        "id": c["id"],
        "platform": PLATFORMS[c["platform"]],
        "name": c.get("name"),
        "followers": c.get("followers"),
        "country": c.get("country") or None,
        "language": c.get("language") or None,
        "bio": (c.get("bio") or "")[:200],
        "posts": [f"p{i + 1}: {(p.get('title') or '')[:80]}" for i, p in enumerate(c.get("recent_posts", [])[:6])],
    }


def _local_why(c: dict, reasons: list) -> list[dict]:
    out = []
    for text in reasons or []:
        text = str(text).strip()
        sign = "-" if text.startswith("-") else "+"
        refs = [f"{k}{n}" for k, n in REF_RE.findall(text)]
        r = _resolve(c, "content", sign, text.lstrip("-+ "), [x for x in refs if x[0].lower() == "p"], [], "ai")
        if r:
            out.append(r)
    return out[:2]


async def score_batch(company: dict, search: dict, creators: list[dict], ai: dict | None = None) -> dict[str, dict]:
    ai = ai or settings.ai_config()
    by_id = {c["id"]: c for c in creators}
    if ai["local"]:
        system = LOCAL_SCORE_SYSTEM + "\n\n" + brand_block(company, search, past_limit=12)
        user = "Creators:\n" + json.dumps([_compact_local(c) for c in creators], ensure_ascii=False)
        data = await _json(system, user, LOCAL_SCORE_SCHEMA, ai=ai, max_tokens=170 * len(creators) + 100)
        out = {}
        for r in data["results"]:
            if isinstance(r, dict) and r.get("id") in by_id:
                r["evidence"] = _local_why(by_id[r["id"]], r.pop("why", []))
                r["red_flags"] = []
                out[r["id"]] = r
        return out
    system = SCORE_SYSTEM + "\n\n" + brand_block(company, search)
    user = "Creators to evaluate:\n" + json.dumps([_compact(c, desc_len=120) for c in creators], ensure_ascii=False)
    data = await _json(system, user, SCORE_SCHEMA, ai=ai, max_tokens=900 * len(creators) + 300)
    out = {}
    for r in data["results"]:
        if isinstance(r, dict) and r.get("id") in by_id:
            r["evidence"] = _evidence(by_id[r["id"]], r.get("evidence"), "ai")
            out[r["id"]] = r
    return out


# --- Deep evaluation (on demand, one creator) ---------------------------------------------------

DEEP_SYSTEM = """You are a senior influencer-marketing manager deciding whether to spend budget on one creator for one brand. Read everything provided: posts with their descriptions, a sample of real viewer comments, audience statistics and authenticity signals. Judge like a careful human would: who the viewers really are (age, interests, buying power, where they live), whether they trust the creator, whether a sponsored segment would feel natural in this creator's format, sponsorship history and saturation, risks, and value for money against the budget.

Return:
- content_fit, audience_fit, market_fit, brand_fit, readiness, brand_safety: 0-100, defined as usual (content = matches the niche wanted; audience = viewers are the brand's customers; market = audience in the target markets; brand = tone and values suit the brand; readiness = contact, sponsor experience without saturation, regular posting, natural format, price within budget; brand_safety 100 = nothing concerning).
- verdict: two sentences, like a note to your team: should we work with them, and why or why not.
- audience_note: one sentence on who watches (likely age range, interests, where they are), and how sure you are.
- collab_idea: one concrete collaboration idea that would feel natural for this creator and this brand.
- sponsors_seen: brand names they have promoted recently (empty if none).
- summary, niche, games, tags: as usual.
- evidence: 4 to 8 claims (dim, sign, claim, posts, comments), each citing the refs (p1.., c1..) that show it. Never cite refs that don't exist. Include the weaknesses too: a score below 100 should have a "-" claim that says why.
Use the whole 0-100 range: reserve 90+ for strong evidence, and give 100 only when there is truly nothing to improve.
- competitor_sponsor: true only if sponsored by one of the brand's competitors.
Judge only from the data provided and never invent facts."""

DEEP_SCHEMA = _obj({
    "content_fit": INT, "audience_fit": INT, "market_fit": INT, "brand_fit": INT, "readiness": INT, "brand_safety": INT,
    "verdict": STR, "audience_note": STR, "collab_idea": STR, "sponsors_seen": STR_LIST,
    "summary": STR, "niche": STR, "games": STR_LIST, "tags": STR_LIST,
    "evidence": EVIDENCE, "competitor_sponsor": BOOL,
})


async def deep_evaluate(company: dict, search: dict, c: dict) -> dict:
    """A thorough, one-creator judgement. Uses the writing AI (usually the stronger, paid one)."""
    ai = settings.writer_config()
    local = ai["local"]
    user = (f"{brand_block(company, search)}\n\nCreator:\n"
            + json.dumps(_compact(c, n_posts=8 if local else 12, n_comments=12 if local else 30, desc_len=150 if local else 300),
                         ensure_ascii=False))
    data = await _json(DEEP_SYSTEM, user, DEEP_SCHEMA, ai=ai, max_tokens=4000)
    data["evidence"] = _evidence(c, data.get("evidence"), "ai")
    data["ai_checked"] = "deep"
    data["model"] = f"{ai['label']} · {active_model(ai)}"
    return data


# --- Search bar: plain words -> filters ---------------------------------------------------------

PARSE_SYSTEM = """You turn a marketer's description of the creators they want into search filters. Use only what the text says; leave everything else empty or 0.
- tags: creator types or content niches mentioned (1-3 words each, Title Case), e.g. "Minecraft", "PC building", "Budget gaming".
- markets: ISO country codes from the allowed list, for countries, nationalities or languages mentioned.
- platforms: "youtube" and/or "tiktok" if mentioned.
- follower_min, follower_max: follower range if mentioned (0 = not said).
- language: ISO 639-1 code if a posting language is asked for, else "".
- has_email: true if they want contact details. growing: true if they want creators growing fast. gems: true for small but very engaged creators.
- rest: any words that are not covered by the fields above (e.g. a creator's name), else ""."""

PARSE_SCHEMA = _obj({
    "tags": STR_LIST, "markets": STR_LIST, "platforms": STR_LIST, "follower_min": INT, "follower_max": INT,
    "language": STR, "has_email": BOOL, "growing": BOOL, "gems": BOOL, "rest": STR,
})


async def parse_query(text: str, known_tags: list[str]) -> dict:
    allowed = ", ".join(f"{code} ({m['name']})" for code, m in MARKETS.items())
    user = f"Allowed market codes: {allowed}\nCreator types this team uses: {', '.join(known_tags) or 'none'}\n\nText: {text}"
    return await _json(PARSE_SYSTEM, user, PARSE_SCHEMA, effort="low", max_tokens=800)


# --- Brand profile from a website -----------------------------------------------------------------

PROFILE_SYSTEM = """You fill in a brand profile for an influencer-marketing team from the text of the company's website. Be concrete and short. Use only what the text supports; leave a field empty ("" or [] or 0) when it doesn't say.
- description: 2-3 sentences: what they sell, to whom, what makes it different, where.
- target_customer: who buys (and who might watch creators that sell it).
- min_audience_age: youngest audience age that makes sense for this product (0 if any age).
- price_range: typical price range of their products, with currency.
- competitors: direct competitors named or clearly implied (company names only).
- values: their tone and what they stand for, in one sentence.
- no_go: kinds of creators or content this brand should clearly avoid.
- goal: "sales", "balanced" or "awareness", whichever suits a company like this best."""

PROFILE_SCHEMA = _obj({
    "description": STR, "target_customer": STR, "min_audience_age": INT, "price_range": STR,
    "competitors": STR_LIST, "values": STR, "no_go": STR_LIST, "goal": {"type": "string", "enum": ["sales", "balanced", "awareness"]},
})
TAG_RE = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


async def profile_from_website(url: str, name: str = "") -> dict:
    if not re.match(r"https?://", url):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 (compatible; Scout brand profile)"}) as http:
            r = await http.get(url)
    except httpx.HTTPError as e:
        raise LLMError(f"Couldn't open {url}: {e}") from e
    if r.status_code >= 400:
        raise LLMError(f"{url} answered with error {r.status_code}")
    text = re.sub(r"\s+", " ", TAG_RE.sub(" ", r.text)).strip()
    if len(text) < 200:
        raise LLMError("That page has almost no text Scout can read (it may need JavaScript). Fill the profile in by hand.")
    user = f"Company: {name or 'unknown'}\nWebsite: {url}\n\nWebsite text:\n{text[:9000]}"
    return await _json(PROFILE_SYSTEM, user, PROFILE_SCHEMA, effort="low", max_tokens=2000)


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
    # On demand (the user clicked), so this may use the better, paid writing AI.
    return await _json(PITCH_SYSTEM, user, PITCH_SCHEMA, ai=settings.writer_config())


# --- Company setup helper --------------------------------------------------------------------

TAGS_SYSTEM = """You help a marketing team decide which social media creators to partner with. Given a company description, suggest 10 short creator types (1-3 words, Sentence case), meaning content niches whose audiences would buy from this company. Mix obvious core niches with a few adjacent, less obvious ones where small creators are easier to find. Don't repeat any of the types the team already has."""


async def suggest_tags(name: str, description: str, existing: list[str]) -> list[str]:
    user = f"Company: {name}\nAbout: {description or 'n/a'}\nAlready have: {', '.join(existing) or 'none'}"
    data = await _json(TAGS_SYSTEM, user, _obj({"tags": STR_LIST}), effort="low", max_tokens=2000)
    have = {t.lower() for t in existing}
    return [t.strip() for t in data["tags"] if isinstance(t, str) and t.strip() and t.lower() not in have][:10]


# --- AI web scout ----------------------------------------------------------------------------

SCOUT_TOOL = {
    "name": "report_creators",
    "description": "Report the creators you found. Call this exactly once, at the end of your research.",
    "strict": True,
    "input_schema": _obj({
        "creators": {"type": "array", "items": _obj({
            "platform": {"type": "string", "enum": list(SEARCH_PLATFORMS)},
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
    ai = settings.scout_config()
    if not ai:
        raise LLMError("The AI web scout needs Claude (as the search or writing AI in Settings)")
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
