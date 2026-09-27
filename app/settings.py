"""User settings from the Settings screen: which AI to use, API keys, data-source keys.

Two AI roles, so the expensive one is only used when it's worth it:
- the search AI plans searches and scores every creator (many calls): a free local model by default;
- the writing AI drafts outreach messages and runs the optional web scout, only when the user clicks
  (for example Claude). If none is set, the search AI does that too.

Saved to data/settings.json on this computer. Values in .env are used as a fallback, so either works.
"""
import json
import os

from .config import DATA_DIR

PATH = DATA_DIR / "settings.json"

# kind "anthropic" uses the Anthropic SDK; kind "openai" speaks the OpenAI-compatible
# chat-completions API, which OpenAI, Gemini, OpenRouter, Ollama and most others offer.
PROVIDERS = {
    "ollama": {
        "label": "Local AI", "company": "free, runs on this computer (Ollama)", "kind": "ollama", "env": "",
        "base_url": "http://localhost:11434", "default_model": "",
        "key_url": "https://ollama.com/download", "needs_key": False, "editable_url": True, "local": True,
        # Small models on a laptop CPU: few creators per request, one request at a time.
        "max_tokens": 4096, "batch_size": 5,
    },
    "anthropic": {
        "label": "Claude", "company": "Anthropic", "kind": "anthropic", "env": "ANTHROPIC_API_KEY",
        "default_model": "claude-opus-5", "key_url": "https://console.anthropic.com/settings/keys",
        "needs_key": True, "web_search": True,
        # Organization-wide keys must name a workspace (sent as the anthropic-workspace-id header).
        "workspace": True,
    },
    "openai": {
        "label": "OpenAI", "company": "GPT models", "kind": "openai", "env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1", "default_model": "gpt-5-mini",
        "key_url": "https://platform.openai.com/api-keys", "needs_key": True,
        "max_tokens_param": "max_completion_tokens", "max_tokens": 16000, "batch_size": 15,
    },
    "gemini": {
        "label": "Gemini", "company": "Google", "kind": "openai", "env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "default_model": "gemini-3.8-flash",
        "key_url": "https://aistudio.google.com/apikey", "needs_key": True,
        # Gemini quotas are per model, so when one runs out (or is overloaded) a lighter one usually still works.
        "fallback_models": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        "max_tokens": 32000, "batch_size": 15,
    },
    "gpu": {
        "label": "Your GPU server", "company": "your own server, e.g. Verda (vLLM)", "kind": "openai",
        "env": "GPU_SERVER_API_KEY", "url_env": "GPU_SERVER_URL",
        "base_url": "", "default_model": "scout", "key_url": "", "needs_key": False, "editable_url": True,
        # A dedicated server costs nothing per request: it checks every creator, several requests at a time,
        # reads full posts and comments, and gets more time per answer than a cloud API.
        "self_hosted": True, "max_tokens": 12000, "batch_size": 6, "concurrency": 8, "timeout": 600,
        "temperature": 0.3,
    },
    "openrouter": {
        "label": "OpenRouter", "company": "many models, one key", "kind": "openai", "env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1", "default_model": "",
        "key_url": "https://openrouter.ai/keys", "needs_key": True,
    },
    "custom": {
        "label": "Custom", "company": "any OpenAI-compatible API", "kind": "openai", "env": "",
        "base_url": "", "default_model": "", "key_url": "", "needs_key": False, "editable_url": True,
    },
}

DATA_KEYS = {
    "youtube_api_key": {"env": "YOUTUBE_API_KEY"},
    "twitch_client_id": {"env": "TWITCH_CLIENT_ID"},
    "twitch_client_secret": {"env": "TWITCH_CLIENT_SECRET"},
}


def load() -> dict:
    if PATH.exists():
        try:
            return json.loads(PATH.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def save(data: dict) -> None:
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, PATH)


def _saved_provider(data: dict, key: str) -> dict:
    return data.get("providers", {}).get(key, {})


def ai_provider(data: dict | None = None) -> str:
    data = load() if data is None else data
    if data.get("ai_provider") in PROVIDERS:
        return data["ai_provider"]
    return "ollama"  # nothing chosen yet: the free local AI


def _same_address(a: str, b: str) -> bool:
    def norm(url: str) -> str:
        return (url or "").strip().rstrip("/").removesuffix("/v1").rstrip("/").lower()
    return norm(a) == norm(b)


def ai_config(provider: str | None = None, overrides: dict | None = None, data: dict | None = None) -> dict:
    """Everything needed to call the chosen AI. `overrides` are unsaved values from the Settings form.

    A saved key is only ever sent to the address it was saved with: a cloud AI's address can't be changed at all,
    and trying a new address for your own server (Test, Load models) needs its key typed again."""
    data = load() if data is None else data
    provider = provider or ai_provider(data)
    p = PROVIDERS[provider]
    saved = _saved_provider(data, provider)
    overrides = {k: v for k, v in (overrides or {}).items() if v}
    editable = p.get("editable_url", False)
    if not editable:
        overrides.pop("base_url", None)
    saved_url = ((saved.get("base_url") if editable else "")
                 or (os.getenv(p["url_env"], "") if p.get("url_env") else "") or p.get("base_url", ""))
    base_url = overrides.get("base_url") or saved_url
    saved_key = saved.get("api_key") or (os.getenv(p["env"]) if p["env"] else "") or ""
    withheld = bool(saved_key and not overrides.get("api_key") and overrides.get("base_url")
                    and not _same_address(overrides["base_url"], saved_url))
    api_key = overrides.get("api_key") or ("" if withheld else saved_key)
    model = overrides.get("model") or saved.get("model") or (
        os.getenv("CLAUDE_MODEL") if provider == "anthropic" else None) or p["default_model"]
    if p["kind"] == "ollama":  # older settings saved the OpenAI-compatible address
        base_url = base_url.rstrip("/").removesuffix("/v1")
    workspace_id = (overrides.get("workspace_id") or saved.get("workspace_id")
                    or (os.getenv("ANTHROPIC_WORKSPACE_ID", "") if p.get("workspace") else "") or "")
    return {
        "provider": provider,
        "label": p["label"],
        "kind": p["kind"],
        "api_key": api_key.strip(),
        "workspace_id": workspace_id.strip(),
        "model": (model or "").strip(),
        "base_url": (base_url or "").strip(),
        "max_tokens_param": p.get("max_tokens_param", "max_tokens"),
        "max_tokens": p.get("max_tokens", 8000),
        # Creators per scoring request: big batches mean fewer requests, which matters on rate-limited free tiers.
        "batch_size": p.get("batch_size", 8 if p["kind"] == "anthropic" else 10),
        "fallback_models": [m for m in p.get("fallback_models", []) if m != (model or "").strip()],
        "web_search": p.get("web_search", False),
        "local": p.get("local", False),
        "self_hosted": p.get("self_hosted", False),
        "concurrency": p.get("concurrency"),
        "timeout": p.get("timeout", 240),
        "temperature": p.get("temperature"),
        "ready": bool(model) and (bool(api_key) or not p["needs_key"]) and (p["kind"] == "anthropic" or bool(base_url)),
        "key_withheld": withheld,  # a new address was typed without its key, so the saved key wasn't used
    }


def writer_provider(data: dict | None = None) -> str:
    """"" = the search AI also writes messages."""
    data = load() if data is None else data
    return data.get("writer_provider") if data.get("writer_provider") in PROVIDERS else ""


def writer_config() -> dict:
    """The AI for on-demand work (outreach messages): the writing AI if it's set up, else the search AI."""
    data = load()
    key = writer_provider(data)
    if key:
        cfg = ai_config(key, data=data)
        if cfg["ready"]:
            return cfg
    return ai_config(data=data)


def scout_config() -> dict | None:
    """The AI web scout needs Claude's web search: the writing AI or the search AI, whichever is Claude."""
    for cfg in (writer_config(), ai_config()):
        if cfg["web_search"] and cfg["ready"]:
            return cfg
    return None


def data_key(name: str, data: dict | None = None) -> str:
    data = load() if data is None else data
    return (data.get(name) or os.getenv(DATA_KEYS[name]["env"], "")).strip()


def youtube_key() -> str:
    return data_key("youtube_api_key")


def twitch_keys() -> tuple[str, str]:
    return data_key("twitch_client_id"), data_key("twitch_client_secret")


def source_status() -> dict:
    ai = ai_config()
    return {
        "ai": ai["ready"],
        "scout": scout_config() is not None,
        "youtube": bool(youtube_key()),
        "tiktok": True,  # Scout's own scraper: no key needed
        "twitch": all(twitch_keys()),  # optional: a free Client ID and Secret
    }


def _mask(value: str) -> str:
    return f"…{value[-4:]}" if len(value) > 8 else ("saved" if value else "")


def public() -> dict:
    """Settings for the UI. Keys are never sent back, only whether one is saved and its last 4 characters."""
    data = load()
    providers = {}
    for key, p in PROVIDERS.items():
        cfg = ai_config(key, data=data)
        providers[key] = {
            "label": p["label"],
            "company": p["company"],
            "key_url": p["key_url"],
            "needs_key": p["needs_key"],
            "editable_url": p.get("editable_url", False),
            "web_search": p.get("web_search", False),
            "key_hint": _mask(cfg["api_key"]),
            "model": cfg["model"],
            "workspace": p.get("workspace", False),
            "workspace_id": cfg["workspace_id"],  # an ID, not a secret
            "default_model": p["default_model"],
            "base_url": cfg["base_url"] if p.get("editable_url") else "",
            # ✓ in the UI only once the user actually set this provider up: a key, or (for keyless ones
            # like Ollama) being the chosen AI. Merely clicking a card saves an empty slot, which isn't "set up".
            "ready": cfg["ready"] and (bool(cfg["api_key"]) or (not p["needs_key"] and key == ai_provider(data))),
            "local": p.get("local", False),
        }
    return {
        "ai_provider": ai_provider(data),
        "writer_provider": writer_provider(data),
        "providers": providers,
        "youtube_key_hint": _mask(data_key("youtube_api_key", data)),
        "twitch_id_hint": _mask(data_key("twitch_client_id", data)),
        "twitch_secret_hint": _mask(data_key("twitch_client_secret", data)),
    }


class SettingsError(ValueError):
    pass


def update(changes: dict) -> None:
    """Apply changes from the Settings form. Empty key fields mean "keep the saved key".
    A new address for an AI that has a key needs the key typed again, so no one who can open Settings can
    point the saved key (or the one in .env) at a server of their own."""
    data = load()
    if changes.get("ai_provider") in PROVIDERS:
        data["ai_provider"] = changes["ai_provider"]
    if changes.get("writer_provider") is not None:
        data["writer_provider"] = changes["writer_provider"] if changes["writer_provider"] in PROVIDERS else ""
    for key, values in (changes.get("providers") or {}).items():
        if key not in PROVIDERS:
            continue
        before = ai_config(key, data=data)
        slot = data.setdefault("providers", {}).setdefault(key, {})
        for field in ("model", "base_url", "workspace_id"):
            if field == "base_url" and not PROVIDERS[key].get("editable_url"):
                continue  # a cloud AI's address is fixed
            if values.get(field) is not None:
                slot[field] = values[field].strip()
        if values.get("api_key"):
            slot["api_key"] = values["api_key"].strip()
        if values.get("clear_key"):
            slot.pop("api_key", None)
        after = ai_config(key, data=data)
        if after["api_key"] and not values.get("api_key") and not _same_address(before["base_url"], after["base_url"]):
            raise SettingsError(f"{PROVIDERS[key]['label']}: type the API key again for the new address. "
                                "A saved key is only sent to the address it was saved with.")
    for name in DATA_KEYS:
        if changes.get(name):
            data[name] = changes[name].strip()
        if changes.get(f"clear_{name}"):
            data.pop(name, None)
    save(data)
