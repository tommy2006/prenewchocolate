"""The search bar: plain words -> filters, instantly and without AI.

"Finnish CS2 youtubers under 50k with email" -> market FI, platform YouTube, creator type CS2,
up to 50,000 followers, has email. Whatever the rules don't understand is returned as `rest`,
which the AI can interpret (on Enter), or which stays a plain text filter.
"""
import re

from .markets import LANGUAGES, MARKETS, PLATFORMS
from .rules import GAMES, NICHES

# Words for each market: English name and adjective, local name and adjective.
COUNTRY_WORDS = {
    "FI": ["finland", "finnish", "finns", "suomi", "suomalainen", "suomalaiset", "suomalaisia"],
    "SE": ["sweden", "swedish", "swedes", "sverige", "svensk", "svenska", "svenske"],
    "NO": ["norway", "norwegian", "norge", "norsk", "norske"],
    "DK": ["denmark", "danish", "danmark", "dansk", "danske"],
    "EE": ["estonia", "estonian", "eesti"],
    "LV": ["latvia", "latvian", "latvija", "latviešu"],
    "LT": ["lithuania", "lithuanian", "lietuva", "lietuvių"],
    "DE": ["germany", "german", "deutschland", "deutsch", "deutsche", "deutschen"],
    "AT": ["austria", "austrian", "österreich", "österreichisch"],
    "CH": ["switzerland", "swiss", "schweiz"],
    "NL": ["netherlands", "dutch", "holland", "nederland", "nederlands"],
    "BE": ["belgium", "belgian", "belgië", "belgique"],
    "FR": ["france", "french", "français", "française"],
    "ES": ["spain", "spanish", "españa", "español"],
    "IT": ["italy", "italian", "italia", "italiano"],
    "PT": ["portugal", "portuguese", "português"],
    "PL": ["poland", "polish", "polska", "polski"],
    "CZ": ["czechia", "czech", "česko", "česky"],
    "HU": ["hungary", "hungarian", "magyar", "magyarország"],
    "GB": ["uk", "britain", "british", "england", "english-speaking uk"],
    "IE": ["ireland", "irish"],
    "US": ["usa", "america", "american", "us-based"],
}
REGIONS = {"nordic": ["FI", "SE", "NO", "DK"], "nordics": ["FI", "SE", "NO", "DK"], "scandinavia": ["SE", "NO", "DK"],
           "scandinavian": ["SE", "NO", "DK"], "baltic": ["EE", "LV", "LT"], "baltics": ["EE", "LV", "LT"],
           "dach": ["DE", "AT", "CH"], "benelux": ["NL", "BE"]}
PLATFORM_WORDS = {"youtube": "youtube", "youtuber": "youtube", "youtubers": "youtube", "yt": "youtube",
                  "tiktok": "tiktok", "tiktoker": "tiktok", "tiktokers": "tiktok", "tik tok": "tiktok"}
TIER_WORDS = {"nano": (1000, 10_000), "micro": (10_000, 50_000), "mid-size": (50_000, 250_000), "midsize": (50_000, 250_000),
              "mid-sized": (50_000, 250_000), "mid": (50_000, 250_000), "macro": (250_000, None), "small": (1000, 50_000),
              "tiny": (500, 10_000), "big": (250_000, None), "large": (250_000, None)}
FLAGS = [
    (r"\b(with|has|have|having)\s+(an?\s+)?(e-?mails?|contact( details| info)?)\b|\bcontactable\b", "has_email"),
    (r"\bhidden gems?\b|\bgems\b|\bsmall but (very )?engaged\b", "gems"),
    (r"\b(growing|rising|trending|up[- ]and[- ]coming|blowing up)\b", "growing"),
    (r"\b(highly |very |most |well[- ])?engaged\b|\bhigh engagement\b", "engaged"),
    (r"\b(english|in english|english[- ]speaking)\b", "english"),
]
FILLER = set("""creator creators channel channels influencer influencers people person accounts account who that with in from
the a an and or for of show me find looking want need i we some any only based speaking posting about followers follower
subscribers subs sub content videos video make makes making do does doing play plays playing on at around like
k m thousand million under below over above than more less least most max min up to between""".split())
# Everyday phrasings of the niches Scout knows.
NICHE_ALIASES = {
    "PC building": r"pc[- ]?build(?:s|er|ers|ing)?|custom pcs?|builds? a pc",
    "Tech reviews": r"tech[- ]?review(?:s|er|ers)?|hardware review(?:s|er|ers)?|unboxing",
    "Budget gaming": r"budget(?: gaming)?|cheap gaming",
    "Gaming setup": r"(?:gaming |desk )?setups?|room tours?",
    "Streaming": r"stream(?:er|ers|ing)",
    "Esports": r"e-?sports?|pro players?",
    "Gaming comedy": r"comedy|funny",
    "Gaming news": r"gaming news",
}
NUM = r"(\d+(?:[.,]\d+)?)\s*(k|m|thousand|million)?"


def _num(value: str, unit: str | None) -> int:
    n = float(value.replace(",", "."))
    unit = (unit or "").lower()
    return int(n * (1000 if unit in ("k", "thousand") else 1_000_000 if unit in ("m", "million") else 1))


def _tag_patterns(known: list[str]) -> list[tuple[str, re.Pattern]]:
    """Creator types to spot: the team's own, every game Scout knows (with its aliases) and the niches."""
    out, seen = [], set()
    for tag in known:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            out.append((tag, re.compile(r"(?<!\w)" + re.escape(tag.lower()) + r"(?!\w)")))
    for game, words in GAMES.items():
        if game.lower() not in seen:
            seen.add(game.lower())
            out.append((game, re.compile(r"(?<!\w)(" + "|".join(re.escape(w) for w in [game.lower(), *words]) + r")(?!\w)")))
    for niche in NICHES:
        alias = NICHE_ALIASES.get(niche)
        pattern = re.escape(niche.lower()) + r"s?" + (f"|{alias}" if alias else "")
        if niche.lower() in seen:  # the team's own tag of the same name: widen it with the aliases
            out = [(tag, re.compile(r"(?<!\w)(" + re.escape(tag.lower()) + "|" + alias + r")(?!\w)")) if alias and tag.lower() == niche.lower()
                   else (tag, p) for tag, p in out]
            continue
        seen.add(niche.lower())
        out.append((niche, re.compile(r"(?<!\w)(" + pattern + r")(?!\w)")))
    return sorted(out, key=lambda t: -len(t[0]))  # "Counter-Strike 2" before "Counter"


def parse(text: str, known_tags: list[str] | None = None) -> dict:
    """Filters found in the text, what they mean in words, and the words left over."""
    t = " " + (text or "").lower().strip() + " "
    f: dict = {}

    def take(span):  # blank out what was understood, so it isn't read twice
        nonlocal t
        t = t[:span[0]] + " " * (span[1] - span[0]) + t[span[1]:]

    # Size first: "under 50k", "10k-50k", "50k+", "at least 5k".
    for pattern, kind in ((rf"\b(?:between\s+)?{NUM}\s*(?:-|–|to|and)\s*{NUM}\b", "range"),
                          (rf"(?:under|below|less than|fewer than|max(?:imum)?|up to|<)\s*{NUM}\b", "max"),
                          (rf"(?:over|above|more than|at least|min(?:imum)?|>)\s*{NUM}\b", "min"),
                          (rf"\b{NUM}\s*\+", "min")):
        m = re.search(pattern, t)
        if not m:
            continue
        g = m.groups()
        if kind == "range":
            lo, hi = _num(g[0], g[1] or g[3]), _num(g[2], g[3])
            f["follower_min"], f["follower_max"] = min(lo, hi), max(lo, hi)
        elif kind == "max":
            f["follower_max"] = _num(g[0], g[1])
        else:
            f["follower_min"] = _num(g[0], g[1])
        take(m.span())
    for word, (lo, hi) in TIER_WORDS.items():
        m = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", t)
        if m and "follower_min" not in f and "follower_max" not in f:
            f["follower_min"], f["follower_max"] = lo, hi
            take(m.span())
            break

    for pattern, flag in FLAGS:
        m = re.search(pattern, t)
        if m:
            if flag == "english":
                f["language"] = "en"
            else:
                f[flag] = True
            take(m.span())

    markets = []
    for region, codes in REGIONS.items():
        m = re.search(rf"(?<!\w){region}(?!\w)", t)
        if m:
            markets += [c for c in codes if c not in markets]
            take(m.span())
    for code, words in COUNTRY_WORDS.items():
        for w in sorted(words, key=len, reverse=True):
            m = re.search(rf"(?<!\w){re.escape(w)}(?!\w)", t)
            if m:
                if code not in markets:
                    markets.append(code)
                take(m.span())
    if markets:
        f["markets"] = markets

    platforms = []
    for w, p in sorted(PLATFORM_WORDS.items(), key=lambda kv: -len(kv[0])):
        m = re.search(rf"(?<!\w){re.escape(w)}(?!\w)", t)
        if m:
            if p not in platforms:
                platforms.append(p)
            take(m.span())
    if platforms:
        f["platforms"] = platforms

    tags = []
    for tag, pattern in _tag_patterns(known_tags or []):
        m = pattern.search(t)
        if m:
            tags.append(tag)
            take(m.span())
    if tags:
        f["tags"] = tags

    rest = " ".join(w for w in re.findall(r"[\w'.@-]+", t) if w not in FILLER and len(w) > 1)
    return {"filters": f, "rest": rest, "understood": describe(f)}


def describe(f: dict) -> list[str]:
    """The filters in words, for the line under the search bar."""
    parts = []
    if f.get("markets"):
        parts.append(", ".join(MARKETS[m]["name"] for m in f["markets"] if m in MARKETS))
    if f.get("platforms"):
        parts.append(" + ".join(PLATFORMS.get(p, p) for p in f["platforms"]))
    if f.get("tags"):
        parts.append(", ".join(f["tags"]))
    if f.get("follower_min") or f.get("follower_max"):
        parts.append(size_text(f.get("follower_min"), f.get("follower_max")))
    for key, label in (("has_email", "has email"), ("gems", "hidden gems"), ("growing", "growing"), ("engaged", "engaged")):
        if f.get(key):
            parts.append(label)
    if f.get("language"):
        parts.append(f"posts in {LANGUAGES.get(f['language'], f['language'])}")
    return parts


def _short(n: int) -> str:
    return f"{n / 1e6:g}M" if n >= 1e6 else f"{n / 1e3:g}k" if n >= 1e3 else str(n)


def size_text(lo: int | None, hi: int | None) -> str:
    if lo and hi:
        return f"{_short(lo)}–{_short(hi)} followers"
    if hi:
        return f"up to {_short(hi)} followers"
    return f"{_short(lo or 0)}+ followers"
