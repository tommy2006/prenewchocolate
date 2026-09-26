"""Free, instant scoring without any AI: games, niche, market, brand-safety flags and reasons,
from the facts the platforms already give us (language, country, post titles, stats).

Every creator gets this score straight away. The AI then only re-checks the most promising ones,
which keeps a search to minutes on a laptop's local model and costs nothing on a paid one.
"""
import re

from .markets import LANGUAGES, MARKETS, PLATFORMS

# Game -> patterns (lowercase, matched on word boundaries) in titles, hashtags and bio.
GAMES = {
    "Minecraft": ["minecraft", "mc survival", "hypixel"],
    "Fortnite": ["fortnite"],
    "GTA": ["gta", "gta rp", "gtarp", "grand theft auto", "gta 5", "gta v", "gta 6", "fivem"],
    "Roblox": ["roblox"],
    "Counter-Strike 2": ["cs2", "counter-strike", "counter strike", "csgo", "cs:go", "cs go"],
    "Valorant": ["valorant"],
    "League of Legends": ["league of legends", "leagueoflegends"],
    "ARK": ["ark survival", "ark ascended", "arksurvival", "ark:"],
    "Clash Royale": ["clash royale", "clashroyale"],
    "Clash of Clans": ["clash of clans", "clashofclans"],
    "Brawl Stars": ["brawl stars", "brawlstars"],
    "Call of Duty": ["call of duty", "warzone", "black ops", "callofduty"],
    "Apex Legends": ["apex legends", "apexlegends"],
    "EA Sports FC": ["ea fc", "ea sports fc", "fc 25", "fc 26", "fc25", "fc26", "fifa", "ultimate team"],
    "Rocket League": ["rocket league", "rocketleague"],
    "Overwatch": ["overwatch"],
    "Dota 2": ["dota 2", "dota2"],
    "Elden Ring": ["elden ring", "eldenring", "nightreign"],
    "Dark Souls": ["dark souls", "darksouls", "soulslike", "souls-like"],
    "The Sims": ["the sims", "sims 4", "sims4"],
    "Pokémon": ["pokemon", "pokémon"],
    "Rainbow Six Siege": ["rainbow six", "r6 siege", "r6s"],
    "PUBG": ["pubg"],
    "Among Us": ["among us"],
    "Genshin Impact": ["genshin"],
    "Terraria": ["terraria"],
    "Stardew Valley": ["stardew"],
    "Battlefield": ["battlefield"],
    "Marvel Rivals": ["marvel rivals"],
    "Escape from Tarkov": ["tarkov"],
    "World of Warcraft": ["world of warcraft", "wow classic"],
    "Rust": ["rust console", "rust pvp", "rust base", "playrust"],
    "Geometry Dash": ["geometry dash"],
    "Helldivers 2": ["helldivers"],
    "Palworld": ["palworld"],
    "Hollow Knight": ["hollow knight", "silksong"],
    "Euro Truck Simulator": ["euro truck", "ets2"],
    "Farming Simulator": ["farming simulator", "farming sim", "fs25", "fs22"],
    "Assetto Corsa": ["assetto corsa"],
    "iRacing": ["iracing", "sim racing", "simracing"],
}

# Niche -> keywords in several of the markets' languages.
NICHES = {
    "PC building": ["pc build", "build a pc", "building a pc", "custom pc", "gaming pc", "pc setup", "pelikone",
                    "pelitietokone", "tietokone", "kokoonpano", "speldator", "gamingdator", "bygga dator",
                    "gaming-pc", "gaming pc bauen", "pc zusammenbauen", "komputer", "zestaw pc", "pc-bygge",
                    "rtx", "radeon", "geforce", "graphics card", "näytönohjain", "grafikkarte", "grafikkort"],
    "Tech reviews": ["review", "unboxing", "arvostelu", "testissä", "recension", "testbericht", "im test",
                     "recenzja", "anmeldelse", "tech tips", "tekniikka", "teknik", "technik"],
    "Gaming setup": ["setup", "desk setup", "room tour", "huonekierros", "pelihuone", "gaming room", "setup tour"],
    "Gaming news": ["gaming news", "peliuutiset", "spelnyheter", "gaming nyheder", "nachrichten", "news"],
    "Streaming": ["twitch", "stream", "livestream", "striimi", "live"],
    "Esports": ["esports", "e-sports", "tournament", "turnaus", "turnering", "pro player"],
    "Gaming comedy": ["funny", "hauska", "rolig", "lustig", "meme", "prank", "comedy"],
    "Budget gaming": ["budget", "cheap", "halpa", "edullinen", "billig", "günstig", "tani", "used", "käytetty",
                      "begagnad", "gebraucht", "refurbished", "second hand"],
}
GAMING_WORDS = re.compile(r"\b(gaming|gamer|gameplay|pelaa|pelit|pelaaja|gamer|spel|spiele|zocken|gra[mć]?)\b", re.I)

GAMBLING = re.compile(r"\b(casino|kasino|betting|vedonly\w*|bet365|stake\.com|gamdom|rollbit|csgoempire|hellcase|"
                      r"skinclub|case opening|skin gambling|roobet)\b", re.I)
ADULT = re.compile(r"\b(onlyfans|nsfw|18\+ only)\b", re.I)


def _patterns(words: list[str]) -> re.Pattern:
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in words) + r")(?![\w])", re.I)


_GAME_RE = {game: _patterns(words) for game, words in GAMES.items()}
_NICHE_RE = {niche: _patterns(words) for niche, words in NICHES.items()}


def _texts(c: dict) -> list[str]:
    return [p.get("title") or "" for p in c.get("recent_posts", [])[:12]]


def games(c: dict) -> list[tuple[str, int]]:
    """(game, number of recent posts that mention it), most mentioned first."""
    texts, bio = _texts(c), c.get("bio") or ""
    found = []
    for game, pattern in _GAME_RE.items():
        n = sum(1 for t in texts if pattern.search(t))
        if n or pattern.search(bio):
            found.append((game, n))
    return sorted(found, key=lambda g: -g[1])


def niche(c: dict, found_games: list[tuple[str, int]]) -> str:
    text = " ".join(_texts(c)) + " " + (c.get("bio") or "")
    hits = {n: len(p.findall(text)) for n, p in _NICHE_RE.items()}
    best = max(hits, key=hits.get)
    if hits[best] >= 2:
        return best
    if found_games or GAMING_WORDS.search(text):
        return "Gaming"
    return best if hits[best] else ""


def market_fit(c: dict, markets: list[str]) -> tuple[int, str]:
    """0-100 and a reason, from the country and language the platform reports."""
    country, lang = c.get("country") or "", c.get("language") or ""
    langs = {l for m in markets if m in MARKETS for l in MARKETS[m]["languages"]}
    if country and country in markets:
        return 90, f"Based in {MARKETS[country]['name']}"
    if country and country not in markets:
        return 15, f"Based outside your markets ({country})"
    if lang and lang in langs and lang != "en":
        return 80, f"Posts in {LANGUAGES.get(lang, lang)}"
    if lang == "en":
        return 40, "Posts in English; country unknown"
    return 50, ""


def _tag_hits(tag: str, text: str, found_games: list[str], niche_name: str) -> bool:
    t = tag.lower().strip()
    if not t:
        return False
    if t in (g.lower() for g in found_games) or t == niche_name.lower():
        return True
    words = [w for w in re.split(r"[\s/&,-]+", t) if len(w) >= 3]
    return bool(words) and all(re.search(r"(?<!\w)" + re.escape(w), text) for w in words)


def quick_score(c: dict, company: dict, search: dict) -> dict:
    """The same fields the AI returns, filled in by rules. `ai_checked` is False so the UI can say so."""
    found = games(c)
    game_names = [g for g, _ in found][:4]
    niche_name = niche(c, found)
    text = (" ".join(_texts(c)) + " " + (c.get("bio") or "")).lower()
    wanted = [t for t in (search.get("tags") or []) if t] or company.get("suggested_tags", [])[:6]
    focus = [w for w in re.split(r"\W+", (search.get("focus") or "").lower()) if len(w) >= 3]
    matched = [t for t in wanted if _tag_hits(t, text, game_names, niche_name)]
    focus_hit = bool(focus) and all(w in text for w in focus)

    gaming = bool(found) or niche_name not in ("", "Tech reviews") or bool(GAMING_WORDS.search(text))
    # No sign of the wanted niche at all (news outlets, lifestyle accounts) should sink, not float on engagement.
    niche_fit = 20 + (25 if gaming else 0) + min(40, 20 * len(matched)) + (15 if focus_hit else 0)
    main_game_share = (found[0][1] / max(1, len(_texts(c)))) if found else 0
    if matched and main_game_share >= 0.4:
        niche_fit += 5  # posts about it regularly, not once
    niche_fit = min(85, niche_fit)  # rules can't be sure; the AI may confirm higher

    markets = search.get("markets") or []
    mfit, market_reason = market_fit(c, markets)

    flags, safety = [], 100
    posts_text = " ".join(_texts(c)) + " " + (c.get("bio") or "")
    if GAMBLING.search(posts_text):
        flags.append("Mentions gambling or skin-betting sites")
        safety -= 45
    if ADULT.search(posts_text):
        flags.append("Adult content signals")
        safety -= 50
    if (c.get("days_since_last_post") or 0) > 60:
        flags.append(f"Quiet lately: last post {c['days_since_last_post']} days ago")

    brand = (company.get("name") or "").lower()
    worked = bool(brand) and len(brand) >= 4 and re.search(r"(?<!\w)#?" + re.escape(brand) + r"(?!\w)", text)

    why = []
    if found and found[0][1] >= 2:
        why.append(f"Posts about {found[0][0]} ({found[0][1]} of their last {len(_texts(c))} posts)")
    elif matched:
        why.append(f"Content matches {', '.join(matched[:2])}")
    if market_reason and mfit >= 80:
        why.append(market_reason)
    vs = c.get("engagement_vs_typical")
    if vs and vs >= 1.2:
        why.append(f"Engagement {vs}× typical for their size")
    trend = c.get("views_trend")
    if trend is not None and trend >= 0.25:
        why.append(f"Views up {round(trend * 100)}% in the last 30 days")
    if worked:
        why.append(f"Has mentioned {company['name']} in a post")

    lang = c.get("language") or ""
    who = " ".join(x for x in (LANGUAGES.get(lang, ""), PLATFORMS[c["platform"]], "creator") if x)
    about = " and ".join(game_names[:2]) if game_names else (niche_name or "")
    views = c.get("avg_views")
    summary = who + (f" posting {about}" if about else "") + (f"; about {_short(views)} views per video" if views else "")

    return {
        "niche_fit": niche_fit,
        "market_fit": mfit,
        "brand_safety": max(0, safety),
        "language": lang,
        "country": c.get("country") or "",
        "summary": summary[:1].upper() + summary[1:],
        "niche": niche_name,
        "games": game_names,
        "tags": list(dict.fromkeys(game_names[:3] + ([niche_name] if niche_name else [])))[:4],
        "matched_tags": matched,
        "why": why[:3],
        "red_flags": flags,
        "competitor_sponsor": False,
        "ai_checked": False,
    }


def _short(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)


# A word that makes a web or YouTube search local, per market.
LOCAL_WORD = {
    "FI": "suomi", "SE": "svenska", "NO": "norsk", "DK": "dansk", "EE": "eesti", "LV": "latvija", "LT": "lietuva",
    "DE": "deutsch", "AT": "österreich", "CH": "schweiz", "NL": "nederlands", "BE": "belgië", "FR": "français",
    "ES": "español", "IT": "italiano", "PT": "português", "PL": "polska", "CZ": "česky", "HU": "magyar",
    "GB": "uk", "IE": "ireland", "US": "usa",
}


def template_plan(company: dict, search: dict, platforms: list[str]) -> list[dict]:
    """Search terms without any AI: each creator type (or the focus) plus the market's local word."""
    terms = [t for t in (search.get("tags") or []) if t] or company.get("suggested_tags", [])[:4] or ["gaming"]
    if search.get("focus"):
        terms = [search["focus"]] + terms
    plans = []
    for m in search.get("markets") or []:
        word = LOCAL_WORD.get(m, "")
        queries = [f"{t.lower()} {word}".strip() for t in terms][:4]
        plans.append({
            "market": m,
            "youtube_queries": queries if "youtube" in platforms else [],
            "tiktok_queries": queries if "tiktok" in platforms else [],
            "tiktok_hashtags": [re.sub(r"\W", "", f"{t}{word}".lower()) for t in terms][:2] if "tiktok" in platforms else [],
        })
    return plans
