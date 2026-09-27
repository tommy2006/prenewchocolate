"""Static reference data shared by the backend and the UI (served at /api/meta)."""

MARKETS = {
    "FI": {"name": "Finland", "languages": ["fi", "sv"]},
    "SE": {"name": "Sweden", "languages": ["sv"]},
    "NO": {"name": "Norway", "languages": ["no"]},
    "DK": {"name": "Denmark", "languages": ["da"]},
    "IS": {"name": "Iceland", "languages": ["is"]},
    "EE": {"name": "Estonia", "languages": ["et"]},
    "LV": {"name": "Latvia", "languages": ["lv"]},
    "LT": {"name": "Lithuania", "languages": ["lt"]},
    "DE": {"name": "Germany", "languages": ["de"]},
    "AT": {"name": "Austria", "languages": ["de"]},
    "CH": {"name": "Switzerland", "languages": ["de", "fr", "it"]},
    "NL": {"name": "Netherlands", "languages": ["nl"]},
    "BE": {"name": "Belgium", "languages": ["nl", "fr"]},
    "LU": {"name": "Luxembourg", "languages": ["fr", "de"]},
    "FR": {"name": "France", "languages": ["fr"]},
    "ES": {"name": "Spain", "languages": ["es"]},
    "IT": {"name": "Italy", "languages": ["it"]},
    "PT": {"name": "Portugal", "languages": ["pt"]},
    "PL": {"name": "Poland", "languages": ["pl"]},
    "CZ": {"name": "Czechia", "languages": ["cs"]},
    "SK": {"name": "Slovakia", "languages": ["sk"]},
    "HU": {"name": "Hungary", "languages": ["hu"]},
    "SI": {"name": "Slovenia", "languages": ["sl"]},
    "HR": {"name": "Croatia", "languages": ["hr"]},
    "RO": {"name": "Romania", "languages": ["ro"]},
    "BG": {"name": "Bulgaria", "languages": ["bg"]},
    "GR": {"name": "Greece", "languages": ["el"]},
    "GB": {"name": "United Kingdom", "languages": ["en"]},
    "IE": {"name": "Ireland", "languages": ["en"]},
    "US": {"name": "United States", "languages": ["en"]},
}

LANGUAGES = {
    "fi": "Finnish", "sv": "Swedish", "no": "Norwegian", "da": "Danish", "is": "Icelandic", "et": "Estonian",
    "lv": "Latvian", "lt": "Lithuanian", "hu": "Hungarian",
    "de": "German", "nl": "Dutch", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "pl": "Polish", "cs": "Czech", "sk": "Slovak", "sl": "Slovenian", "hr": "Croatian",
    "ro": "Romanian", "bg": "Bulgarian", "el": "Greek", "en": "English",
}

PLATFORMS = {"youtube": "YouTube", "tiktok": "TikTok", "twitch": "Twitch", "instagram": "Instagram"}
# What a search can cover. Instagram only shows up as a linked profile (contact details, export).
SEARCH_PLATFORMS = {"youtube": "YouTube", "tiktok": "TikTok", "twitch": "Twitch"}  # Twitch: optional, needs keys

# (key, min followers, max followers, label)
TIERS = [
    ("nano", 0, 10_000, "Nano"),
    ("micro", 10_000, 50_000, "Micro"),
    ("mid", 50_000, 250_000, "Mid"),
    ("macro", 250_000, None, "Macro"),
]

DEAL_TYPES = ["Gifted product", "Affiliate / discount code", "Paid post", "Long-term ambassador", "Giveaway"]


def tier_of(followers: int | None) -> str | None:
    if followers is None:
        return None
    for key, lo, hi, _ in TIERS:
        if followers >= lo and (hi is None or followers < hi):
            return key
    return None
