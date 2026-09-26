"""Free, instant scoring without any AI: games, niche, market, brand-safety flags and reasons,
from the facts the platforms already give us (language, country, post titles, stats).

Every creator gets this score straight away. The AI then only re-checks the most promising ones,
which keeps a search to minutes on a laptop's local model and costs nothing on a paid one.
"""
import re

from . import audience as audience_mod, scoring
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


# Official PEGI age ratings (Europe) of the games in GAMES; games without a clear rating are left out.
# A clue to the audience's age, not a rule: many adults play Minecraft too.
GAME_AGE = {
    "Minecraft": 7, "Roblox": 7, "Brawl Stars": 7, "Clash Royale": 7, "Clash of Clans": 7, "Among Us": 7, "Pokémon": 7,
    "Stardew Valley": 7, "Hollow Knight": 7,
    "Fortnite": 12, "League of Legends": 12, "Overwatch": 12, "The Sims": 12, "Genshin Impact": 12, "Terraria": 12,
    "World of Warcraft": 12,
    "Valorant": 16, "Apex Legends": 16, "Elden Ring": 16, "Dark Souls": 16,
    "GTA": 18, "Counter-Strike 2": 18, "Call of Duty": 18, "Rainbow Six Siege": 18, "Battlefield": 18, "Helldivers 2": 18,
    "EA Sports FC": 3, "Rocket League": 3, "Euro Truck Simulator": 3, "Farming Simulator": 3, "Assetto Corsa": 3,
}
AGE_LABEL = {"young": "Skews young (many under 13)", "teen": "Mostly teenagers", "older": "Mostly 16+", "mixed": "Mixed ages"}


def age_estimate(c: dict, found: list[tuple[str, int]] | None = None) -> dict:
    """Who is likely watching, from two clues: the age ratings of the games they post about, and what commenters
    say about themselves (school vs work, stated ages). {"band", "label", "clues": [...]}; band "" = no clue."""
    found = games(c) if found is None else found
    n_posts = max(1, len(_texts(c)))
    by_band = {"young": 0, "teen": 0, "older": 0}
    for game, n in found:
        rating = GAME_AGE.get(game)
        if rating is not None and rating >= 7:
            by_band["young" if rating <= 7 else "teen" if rating == 12 else "older"] += n
    votes, clues = [], []
    band, n = max(by_band.items(), key=lambda kv: kv[1])
    if n / n_posts >= 0.3:
        rated = [f"{g} (PEGI {GAME_AGE[g]})" for g, k in found if k and g in GAME_AGE and GAME_AGE[g] >= 7][:2]
        votes.append(band)
        clues.append(f"Games: mostly {', '.join(rated)}")
    a = c.get("audience") or {}
    sampled = a.get("sampled") or 0
    if sampled >= 20:
        young, adult = a.get("young_hints") or 0, a.get("adult_hints") or 0
        if young >= 3 and young / sampled >= 0.04 and young > adult:
            votes.append("young")
            clues.append(f"Comments: {young} of {sampled} mention school or an age under 16")
        elif adult >= 3 and adult / sampled >= 0.03 and adult > young:
            votes.append("older")
            clues.append(f"Comments: {adult} of {sampled} mention work, partners, their own kids or an adult age")
    if not votes:
        return {"band": "", "label": "Unclear", "clues": []}
    final = votes[0] if len(set(votes)) == 1 else "mixed"
    return {"band": final, "label": AGE_LABEL[final], "clues": clues}


def comment_quotes(c: dict, kind: str, n: int = 2) -> list[str]:
    """Example comments behind a clue ("young", "adult", "buying"), for the evidence."""
    sample = c.get("comment_sample") or []
    idx = ((c.get("audience") or {}).get("notable") or {}).get(kind) or []
    return [sample[i]["text"][:140] for i in idx[:n] if i < len(sample)]


# Content that means viewers are shopping for hardware.
BUYER_NICHES = {"PC building", "Tech reviews", "Gaming setup", "Budget gaming"}


def _posts_matching(c: dict, pattern: re.Pattern) -> list[dict]:
    return [p for p in c.get("recent_posts", [])[:12] if pattern.search(f"{p.get('title') or ''} {p.get('desc') or ''}")]


def _market_langs(markets: list[str]) -> set[str]:
    return {l for m in markets if m in MARKETS for l in MARKETS[m]["languages"]}


def quick_score(c: dict, company: dict, search: dict) -> dict:
    """The same fields the AI returns, filled in by rules, each score with the evidence behind it.
    `ai_checked` is False so the UI can say it's a quick score."""
    profile = company.get("profile") or {}
    posts = c.get("recent_posts", [])[:12]
    found = games(c)
    game_names = [g for g, _ in found][:4]
    niche_name = niche(c, found)
    text = (" ".join(_texts(c)) + " " + (c.get("bio") or "")).lower()
    wanted = [t for t in (search.get("tags") or []) if t] or company.get("suggested_tags", [])[:6]
    focus = [w for w in re.split(r"\W+", (search.get("focus") or "").lower()) if len(w) >= 3]
    matched = [t for t in wanted if _tag_hits(t, text, game_names, niche_name)]
    focus_hit = bool(focus) and all(w in text for w in focus)
    ev = []

    # Content: do their posts match what's wanted?
    gaming = bool(found) or niche_name not in ("", "Tech reviews") or bool(GAMING_WORDS.search(text))
    content = 20 + (25 if gaming else 0) + min(40, 20 * len(matched)) + (15 if focus_hit else 0)
    main_game_share = (found[0][1] / max(1, len(_texts(c)))) if found else 0
    if matched and main_game_share >= 0.4:
        content += 5  # posts about it regularly, not once
    content = min(85, content)  # rules can't be sure; the AI may confirm higher
    if found and found[0][1] >= 2:
        ev.append(scoring.evidence_item("content", "+", f"Posts about {found[0][0]} in {found[0][1]} of their last {len(_texts(c))} posts",
                                        scoring.cite(_posts_matching(c, _GAME_RE[found[0][0]])), fact=False))
    if matched:
        hits = [p for p in posts if any(_tag_hits(t, (p.get("title") or "").lower(), [], "") for t in matched)]
        ev.append(scoring.evidence_item("content", "+", f"Content matches {', '.join(matched[:3])}", scoring.cite(hits), fact=False))
    elif wanted and not gaming:
        ev.append(scoring.evidence_item("content", "-", f"No sign of {', '.join(wanted[:3])} in their recent posts", fact=False))

    # Audience: would the people watching actually buy? Age (game ratings, what commenters say), buying interest.
    audience, a = 55, c.get("audience") or {}
    min_age = profile.get("min_audience_age") or 0
    rated = [(g, n) for g, n in found if n and GAME_AGE.get(g, 0) >= 7]
    age = age_estimate(c, found)
    if rated and age["clues"] and age["clues"][0].startswith("Games"):
        top = rated[0][0]
        posts_cited = scoring.cite(_posts_matching(c, _GAME_RE[top]))
        if GAME_AGE[top] <= 7:
            audience -= 15 if min_age >= 13 else 8
            ev.append(scoring.evidence_item("audience", "-", f"Mostly {top} (PEGI {GAME_AGE[top]}): games rated for age 7 and up draw many young viewers", posts_cited))
        elif GAME_AGE[top] >= 16:
            audience += 10
            ev.append(scoring.evidence_item("audience", "+", f"Mostly {top} (PEGI {GAME_AGE[top]}): viewers are more likely old enough to buy", posts_cited))
    if (a.get("sampled") or 0) >= 20:
        sampled, young, adult = a["sampled"], a.get("young_hints") or 0, a.get("adult_hints") or 0
        if young >= 3 and young / sampled >= 0.04 and young > adult:
            audience -= 10
            ev.append(scoring.evidence_item("audience", "-", f"{young} of {sampled} sampled comments mention school or an age under 16",
                                            quotes=comment_quotes(c, "young")))
        elif adult >= 3 and adult / sampled >= 0.03 and adult > young:
            audience += 5
            ev.append(scoring.evidence_item("audience", "+", f"{adult} of {sampled} sampled comments mention work, partners, their own kids or an adult age",
                                            quotes=comment_quotes(c, "adult")))
    buyer_posts = [p for n in BUYER_NICHES for p in _posts_matching(c, _NICHE_RE[n])]
    if len(buyer_posts) >= 2:
        audience += 15
        ev.append(scoring.evidence_item("audience", "+", "Talks about PC hardware and setups: viewers are shopping for gear",
                                        scoring.cite(list({p.get("url"): p for p in buyer_posts}.values())), fact=False))
    if (a.get("sampled") or 0) >= 15:
        buying = a.get("buying_questions") or 0
        if buying >= 2 and buying / a["sampled"] >= 0.03:
            audience += 10
            ev.append(scoring.evidence_item("audience", "+", f"Viewers ask what to buy: {buying} of {a['sampled']} sampled comments ask about specs, prices or where to get it",
                                            quotes=comment_quotes(c, "buying")))
        elif a.get("question_share", 0) >= 0.12:
            audience += 5
    audience = max(20, min(85, audience))

    # Market: where the creator and their audience are.
    markets = search.get("markets") or []
    market, market_reason = market_fit(c, markets)
    if market_reason:
        ev.append(scoring.evidence_item("market", "+" if market >= 60 else "-", market_reason + " (platform data)"))
    langs = a.get("languages") or {}
    if (a.get("detected") or 0) >= 10 and markets:
        wanted_langs = _market_langs(markets)
        share = sum(v for k, v in langs.items() if k in wanted_langs and (k != "en" or "en" in wanted_langs))
        top = next(iter(langs), "")
        if share >= 0.5:
            market = max(market, 85)
            names = ", ".join(LANGUAGES.get(k, k) for k in langs if k in wanted_langs)
            ev.append(scoring.evidence_item("market", "+", f"{share:.0%} of sampled comments are in {names}"))
        elif share < 0.15 and top and top not in wanted_langs and top != "en":
            market = min(market, 40)
            ev.append(scoring.evidence_item("market", "-", f"Most sampled comments are in {LANGUAGES.get(top, top)}"))

    # Brand & safety: tone, risks, competitors.
    brand, safety, competitor = 75, 100, False
    gambling = _posts_matching(c, GAMBLING)
    if gambling or GAMBLING.search(c.get("bio") or ""):
        safety -= 45
        ev.append(scoring.evidence_item("brand", "-", "Mentions gambling or skin-betting sites", scoring.cite(gambling)))
    adult = _posts_matching(c, ADULT)
    if adult or ADULT.search(c.get("bio") or ""):
        safety -= 50
        ev.append(scoring.evidence_item("brand", "-", "Adult content signals", scoring.cite(adult)))
    for name in profile.get("competitors") or []:
        if len(name) < 3:
            continue
        pattern = re.compile(r"(?<!\w)#?" + re.escape(name.lower()).replace(r"\ ", r"\s?") + r"(?!\w)", re.I)
        hits = _posts_matching(c, pattern)
        if hits or pattern.search(c.get("bio") or ""):
            sponsored = [p for p in hits if audience_mod.DISCLOSURE.search(f"{p.get('title') or ''} {p.get('desc') or ''}")]
            competitor = competitor or bool(sponsored)
            brand -= 25 if sponsored else 10
            ev.append(scoring.evidence_item("brand", "-", f"{'Sponsored by' if sponsored else 'Mentions'} {name}, a competitor",
                                            scoring.cite(sponsored or hits)))
    brand_name = (company.get("name") or "").lower()
    if len(brand_name) >= 4:
        own = _posts_matching(c, re.compile(r"(?<!\w)#?" + re.escape(brand_name) + r"(?!\w)", re.I))
        if own:
            brand += 10
            ev.append(scoring.evidence_item("brand", "+", f"Has mentioned {company['name']} before", scoring.cite(own)))
    brand = max(0, min(100, min(brand, safety + 10)))
    checked_posts = len(c.get("recent_posts") or [])
    if checked_posts and not any(e["dim"] == "brand" for e in ev):
        ev.append(scoring.evidence_item("brand", "+", f"No gambling, adult content or competitor mentions in their last {checked_posts} posts"))

    # Readiness & cost: can we work with them, and can we afford them?
    readiness = 50
    if c.get("emails"):
        readiness += 15
        ev.append(scoring.evidence_item("readiness", "+", "Public business email"))
    else:
        readiness -= 10
        ev.append(scoring.evidence_item("readiness", "-", "No public email: contact them on the platform"))
    sp = c.get("sponsorship") or {}
    if sp.get("sponsored") or sp.get("with_codes"):
        n = max(sp.get("sponsored", 0), sp.get("with_codes", 0))
        if sp.get("checked", 0) >= 6 and n / sp["checked"] >= 0.5:
            readiness -= 10
            ev.append(scoring.evidence_item("readiness", "-", f"Sponsored in {n} of their last {sp['checked']} posts: the audience may be tired of ads",
                                            sp.get("posts")))
        else:
            readiness += 15
            ev.append(scoring.evidence_item("readiness", "+", f"Has done sponsored posts or discount codes ({n} of their last {sp['checked']})",
                                            sp.get("posts")))
    days = c.get("days_since_last_post")
    if (c.get("posts_per_month") or 0) >= 4 and days is not None and days <= 14:
        readiness += 10
    if days is not None and days > 60:
        readiness -= 20
        ev.append(scoring.evidence_item("readiness", "-", f"Quiet lately: last post {days} days ago"))
    price, budget = c.get("price"), profile.get("budget_max")
    if price and budget:
        if price["low"] > budget:
            readiness -= 20
            ev.append(scoring.evidence_item("readiness", "-", f"Likely above budget: about €{price['low']:,}–{price['high']:,} per post vs €{budget:,}"))
        elif price["high"] <= budget:
            readiness += 10
            ev.append(scoring.evidence_item("readiness", "+", f"Fits the budget: about €{price['low']:,}–{price['high']:,} per post"))
    readiness = max(0, min(100, readiness))

    lang = c.get("language") or ""
    who = " ".join(x for x in (LANGUAGES.get(lang, ""), PLATFORMS[c["platform"]], "creator") if x)
    about = " and ".join(game_names[:2]) if game_names else (niche_name or "")
    views = c.get("median_views") or c.get("avg_views")
    summary = who + (f" posting {about}" if about else "") + (f"; about {_short(views)} views per video" if views else "")

    return {
        "content_fit": content,
        "audience_fit": audience,
        "market_fit": market,
        "brand_fit": brand,
        "readiness": readiness,
        "brand_safety": max(0, safety),
        "language": lang,
        "country": c.get("country") or "",
        "summary": summary[:1].upper() + summary[1:],
        "niche": niche_name,
        "games": game_names,
        "tags": list(dict.fromkeys(game_names[:3] + ([niche_name] if niche_name else [])))[:4],
        "matched_tags": matched,
        "evidence": ev,
        "competitor_sponsor": competitor,
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
