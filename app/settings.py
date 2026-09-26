"""User settings from the Settings screen: which AI to use, API keys, data-source keys.

Saved to data/settings.json on this computer. Values in .env are used as a fallback, so either works.
"""
import json
import os

from .config import DATA_DIR

PATH = DATA_DIR / "settings.json"

# kind "anthropic" uses the Anthropic SDK; kind "openai" speaks the OpenAI-compatible
# chat-completions API, which OpenAI, Gemini, OpenRouter, Ollama and most others offer.
PROVIDERS = {
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
    "openrouter": {
        "label": "OpenRouter", "company": "many models, one key", "kind": "openai", "env": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1", "default_model": "",
        "key_url": "https://openrouter.ai/keys", "needs_key": True,
    },
    "ollama": {
        "label": "Ollama", "company": "local, free", "kind": "openai", "env": "",
        "base_url": "http://localhost:11434/v1", "default_model": "llama3.1",
        "key_url": "https://ollama.com/download", "needs_key": False, "editable_url": True,
    },
    "custom": {
        "label": "Custom", "company": "any OpenAI-compatible API", "kind": "openai", "env": "",
        "base_url": "", "default_model": "", "key_url": "", "needs_key": False, "editable_url": True,
    },
}

DATA_KEYS = {
    "youtube_api_key": {"env": "YOUTUBE_API_KEY"},
    "apify_token": {"env": "APIFY_TOKEN"},
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
    # Nothing chosen yet: use the first provider that has a key in .env
    for key, p in PROVIDERS.items():
        if p["env"] and os.getenv(p["env"]):
            return key
    return "anthropic"


def ai_config(provider: str | None = None, overrides: dict | None = None, data: dict | None = None) -> dict:
    """Everything needed to call the chosen AI. `overrides` are unsaved values from the Settings form."""
    data = load() if data is None else data
    provider = provider or ai_provider(data)
    p = PROVIDERS[provider]
    saved = _saved_provider(data, provider)
    overrides = {k: v for k, v in (overrides or {}).items() if v}
    api_key = overrides.get("api_key") or saved.get("api_key") or (os.getenv(p["env"]) if p["env"] else "") or ""
    model = overrides.get("model") or saved.get("model") or (
        os.getenv("CLAUDE_MODEL") if provider == "anthropic" else None) or p["default_model"]
    base_url = overrides.get("base_url") or saved.get("base_url") or p.get("base_url", "")
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
        "ready": bool(model) and (bool(api_key) or not p["needs_key"]) and (p["kind"] == "anthropic" or bool(base_url)),
    }


def data_key(name: str, data: dict | None = None) -> str:
    data = load() if data is None else data
    return (data.get(name) or os.getenv(DATA_KEYS[name]["env"], "")).strip()


def youtube_key() -> str:
    return data_key("youtube_api_key")


def apify_token() -> str:
    return data_key("apify_token")


def source_status() -> dict:
    ai = ai_config()
    apify = bool(apify_token())
    return {
        "ai": ai["ready"],
        "youtube": bool(youtube_key()),
        "tiktok": apify,
        "instagram": apify,
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
        }
    return {
        "ai_provider": ai_provider(data),
        "providers": providers,
        "youtube_key_hint": _mask(data_key("youtube_api_key", data)),
        "apify_token_hint": _mask(data_key("apify_token", data)),
    }


def update(changes: dict) -> None:
    """Apply changes from the Settings form. Empty key fields mean "keep the saved key"."""
    data = load()
    if changes.get("ai_provider") in PROVIDERS:
        data["ai_provider"] = changes["ai_provider"]
    for key, values in (changes.get("providers") or {}).items():
        if key not in PROVIDERS:
            continue
        slot = data.setdefault("providers", {}).setdefault(key, {})
        for field in ("model", "base_url", "workspace_id"):
            if values.get(field) is not None:
                slot[field] = values[field].strip()
        if values.get("api_key"):
            slot["api_key"] = values["api_key"].strip()
        if values.get("clear_key"):
            slot.pop("api_key", None)
    for name in DATA_KEYS:
        if changes.get(name):
            data[name] = changes[name].strip()
        if changes.get(f"clear_{name}"):
            data.pop(name, None)
    save(data)
