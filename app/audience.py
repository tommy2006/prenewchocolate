"""Who is really watching: audience quality from data we already have (no AI).

- comment language (a light stopword guess), generic/spam/duplicate comments, how many different people comment
- authenticity signals: views per follower, likes per view, comments per like, compared with accounts of the same size
- sponsorship: disclosed ads and discount codes in their posts
- a rough price for one sponsored post

Everything here is a *signal*, not proof: the UI says "possible", never "bots detected".
"""
import re
from collections import Counter

from .metrics import TYPICAL_RATE, TYPICAL_REACH

# --- Comment language -------------------------------------------------------------------------

# Short, common words that are distinctive for each language (ambiguous ones left out).
STOPWORDS = {
    "en": "the and you this that what for are with your was have just but not its it's you're really thanks".split(),
    "fi": "ja on se ei että mä sä oli kun tää toi niin mut jo vaan oon mitä hyvä kiitos tosi sun mun ihan kyllä olis tätä mikä miten paras".split(),
    "sv": "och att är jag inte vad mycket också tack det som för har hur bra".split(),
    "no": "ikke hva veldig takk meg deg jeg hvordan også bare".split(),
    "da": "ikke hvad meget tak mig dig jeg hvordan også bare".split(),
    "de": "und ich ist nicht das die der ein eine mit auf sehr auch wie bitte danke geil mal bist habe wir".split(),
    "nl": "het ik niet een van dat je met zijn voor ook wat heel goed bedankt maar dit deze".split(),
    "fr": "le la les et je est pas une des que tu pour avec trop merci c'est très vous mais".split(),
    "es": "el la que es los las por para muy gracias pero como está eres".split(),
    "it": "il che non è sono molto grazie ma come questo anche della".split(),
    "pt": "que não um uma para muito obrigado mas como você isso também".split(),
    "pl": "nie to jest się na że jak co ale bardzo dzięki tak ten już".split(),
    "cs": "je to na se že jak co ale velmi díky jsem taky tak už není".split(),
    "hu": "és az nem hogy egy is van nagyon köszi köszönöm meg de ez már".split(),
    "et": "ja on ei see et ma sa oli väga aitäh kas mis nii ka aga tore".split(),
    "lv": "un ir ne es tu ka kā ar uz paldies ļoti bet arī jā".split(),
    "lt": "ir ne aš tu kad kaip su labai ačiū bet taip jau yra".split(),
}
_WORDS = {lang: set(words) for lang, words in STOPWORDS.items()}
# Letters only some languages use: exclusive ones count more.
LETTERS = {
    "õ": ("et", "pt"), "ą": ("pl", "lt"), "ę": ("pl", "lt"), "ł": ("pl",), "ś": ("pl",), "ź": ("pl",), "ż": ("pl",),
    "ć": ("pl",), "ń": ("pl",), "ř": ("cs",), "ě": ("cs",), "ů": ("cs",), "ő": ("hu",), "ű": ("hu",),
    "ā": ("lv",), "ē": ("lv",), "ī": ("lv",), "ģ": ("lv",), "ķ": ("lv",), "ļ": ("lv",), "ņ": ("lv",),
    "ė": ("lt",), "į": ("lt",), "ų": ("lt",), "ß": ("de",), "ñ": ("es",), "ã": ("pt",),
    "å": ("sv", "no", "da"), "ø": ("no", "da"), "æ": ("no", "da"), "ä": ("fi", "sv", "de", "et"),
    "ö": ("fi", "sv", "de", "et", "hu"),
}
WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def guess_language(text: str) -> str:
    """ISO 639-1 code, or "" when there's too little to tell (emoji, one word, a name)."""
    text = (text or "").lower()
    words = WORD_RE.findall(text)
    if not words:
        return ""
    scores = Counter()
    for w in words:
        for lang, vocab in _WORDS.items():
            if w in vocab:
                scores[lang] += 1
    for ch in set(text):
        langs = LETTERS.get(ch)
        if langs:
            for lang in langs:
                scores[lang] += 1.5 / len(langs)
    if not scores:
        return ""
    (best, top), *rest = scores.most_common(2) + [("", 0)]
    runner_up = rest[0][1] if rest else 0
    return best if top >= 1 and top > runner_up else ""


# --- Comment quality --------------------------------------------------------------------------

GENERIC = set("""nice good great cool wow love it video first lol lmao xd awesome amazing best bro w fire lit gg top super
mega yes omg haha hahaha pog poggers insane sick dope legend king goat the this is so very hyvä hieno siisti mahtava
paras bra snyggt grymt geil stark krass mooi gaaf génial trop bien genial bueno bello fajne dobre szuper tore lahe
forši labai kiva jees jep""".split())
SPAM = re.compile(r"https?://|sub4sub|sub 4 sub|check (out )?my channel|subscribe to me|follow me|telegram|whatsapp|"
                  r"crypto|bitcoin|investment|forex|onlyfans|free robux|free v-?bucks", re.I)
ADVICE = re.compile(r"\b(which|what|recommend|should i|worth it|budget|price|specs?|gpu|cpu|build|kannattaa|mikä|"
                    r"suosittele|vilken|rekommendera|welche|empfehl|lohnt|quelle|conseill|cuál|recomiend|jaki|polecasz|"
                    r"melyik|milline|kurš|kuris)\b", re.I)


# Age clues in comments. Stated ages ("I'm 12", "olen 12", "ich bin 12", "mam 12 lat", "12 éves"...).
AGE_STATED = re.compile(
    r"(?:\b(?:i'?m|i am|im|olen|oon|jag är|jeg er|ich bin|ik ben|ma olen|tengo|ho|j'ai)\s+(\d{1,2})\s*"
    r"(?:years?|yrs?|yo|y/o|vuotias|vuotta|v\b|år|jahre|jaar|aastane|años|anni|ans|and|ja|och|og|und|en|,|\.|!|$))"
    r"|(?:\bmam\s+(\d{1,2})\s*lat\b)|(?:\b(\d{1,2})\s*éves\b)", re.I)
# School and homework: viewers who are still at school.
YOUNG_WORDS = re.compile(
    r"\b(?<!old )(?<!old-)(school|homework|teacher|koulu\w*|läksy\w*|läksyt|opettaj\w*|skola|skolan|läxa\w*|lärare\w*|"
    r"skole\w*|lekse\w*|lærer\w*|schule|hausaufgabe\w*|lehrer\w*|huiswerk|leraar|szkoł\w*|lekcj\w*|nauczyciel\w*|"
    r"iskol\w*|házi|tanár\w*|kooli\w*|kodutöö\w*|õpetaja\w*|école|devoirs|escuela|deberes|scuola|compiti)\b", re.I)
# Work, partners and their own kids: grown-up viewers (who can buy).
ADULT_WORDS = re.compile(
    r"\b(my (wife|husband|kids|son|daughter|boss|job|salary|mortgage)|at work|after work|vaimo\w*|mieheni|lapseni|"
    r"poikani|tyttäreni|töissä|töiden jälkeen|palkka\w*|asuntolaina|min fru|min man|mina barn|på jobbet|efter jobbet|"
    r"lönen|min kone|mine barn|på jobb|meine frau|mein mann|meine kinder|auf der arbeit|nach der arbeit|gehalt|"
    r"mijn vrouw|mijn man|mijn kinderen|op het werk|moja żona|mój mąż|moje dzieci|w pracy|po pracy|feleségem|férjem|"
    r"gyerekeim|munkahelyen|minu naine|minu mees|mu lapsed|ma femme|mon mari|mes enfants|au travail|mi esposa|"
    r"mi marido|mis hijos|en el trabajo|mia moglie|mio marito|i miei figli|al lavoro)\b", re.I)
# Viewers asking what to buy: specs, prices, where to get it. Generic words ("price", "worth it") only count
# in a question, so "totally worth it" or "the price is insane" don't.
BUYING = re.compile(
    r"\b(what|which) (pc|gpu|cpu|graphics card|specs|setup|mouse|keyboard|monitor|headset|computer)|"
    r"your (specs|setup|pc)\b|where did you (buy|get)|how much (did|does|is|was)|should i (buy|get)|"
    r"mistä (ostit|sait|saa)|mikä (kone|näyttis|prosessori|näytönohjain)|kannattaako|vad kostar|var köpte|"
    r"vilken (dator|grafikkort)|hur mycket kostar|hvad koster|hvor køb|was kostet|wo (hast du|gekauft)|"
    r"welche (grafikkarte|gpu|cpu)|hoeveel kost|waar heb je|ile kosztuje|gdzie kupi|jaki (komputer|sprzęt|procesor)|"
    r"mennyibe|hol vetted|milyen (gép|videókártya)|mis maksab|kust ostsid|combien|où as-tu|cuánto cuesta|"
    r"dónde compraste|quanto costa", re.I)
BUYING_WEAK = re.compile(r"\b(price|specs?|worth (buying|it)|hinta|paljonko|speksit|lohnt sich|preis)\b", re.I)


def age_stated(text: str) -> int | None:
    m = AGE_STATED.search(text or "")
    age = next((int(g) for g in (m.groups() if m else ()) if g), None)
    return age if age and 6 <= age <= 70 else None


def _norm_comment(text: str) -> str:
    return " ".join(WORD_RE.findall((text or "").lower()))


def analyze_comments(comments: list[dict]) -> dict | None:
    """Stats over a sample of comments ({"text", "author"}). None when there's nothing to judge."""
    comments = [c for c in comments if (c.get("text") or "").strip()]
    if not comments:
        return None
    n = len(comments)
    langs, generic, spam, questions, advice = Counter(), 0, 0, 0, 0
    texts = Counter()
    notable = {"young": [], "adult": [], "buying": []}  # indices of the comments behind each clue
    for i, c in enumerate(comments):
        text = c["text"]
        words = WORD_RE.findall(text.lower())
        lang = guess_language(text)
        if lang:
            langs[lang] += 1
        if not words or (len(words) <= 3 and all(w in GENERIC for w in words)) or (len(words) == 1 and "?" not in text):
            generic += 1
        if SPAM.search(text):
            spam += 1
        if "?" in text and len(words) >= 3:
            questions += 1
            if ADVICE.search(text):
                advice += 1
        age = age_stated(text)
        if (age and age < 16) or YOUNG_WORDS.search(text):
            notable["young"].append(i)
        elif (age and age >= 18) or ADULT_WORDS.search(text):
            notable["adult"].append(i)
        if BUYING.search(text) or ("?" in text and (BUYING_WEAK.search(text) or (ADVICE.search(text) and len(words) >= 3))):
            notable["buying"].append(i)
        norm = _norm_comment(text)
        if len(norm) >= 8:
            texts[norm] += 1
    authors = [c.get("author") for c in comments if c.get("author")]
    detected = sum(langs.values())
    return {
        "sampled": n,
        "languages": {k: round(v / detected, 2) for k, v in langs.most_common(5)} if detected else {},
        "detected": detected,
        "generic_share": round(generic / n, 2),
        "spam_share": round(spam / n, 2),
        "duplicate_share": round(sum(v - 1 for v in texts.values() if v > 1) / n, 2),
        "unique_authors": round(len(set(authors)) / len(authors), 2) if authors else None,
        "question_share": round(questions / n, 2),
        "advice_share": round(advice / n, 2),
        # Who the commenters are: school vs work (or a stated age), and whether they ask what to buy.
        "young_hints": len(notable["young"]),
        "adult_hints": len(notable["adult"]),
        "buying_questions": len(notable["buying"]),
        "notable": {k: v[:6] for k, v in notable.items()},
    }


# --- Authenticity -----------------------------------------------------------------------------

VERSION = 3  # bump when the assessment changes, so saved creators are re-assessed on start

# Authenticity starts neutral: "nothing suspicious found" is not proof of a real audience. Positive evidence
# raises it, warning signs lower it, and with little data it can't get high at all.
NEUTRAL = 70
CAP = {"low": 75, "medium": 90, "high": 100}


def _signal(kind: str, text: str, penalty: int = 0, bonus: int = 0) -> dict:
    return {"kind": kind, "text": text, "penalty": penalty, "bonus": bonus}


def authenticity(c: dict) -> dict:
    """0-100 (100 = nothing suspicious), the signals behind it, and how much data it rests on."""
    platform, tier = c["platform"], c.get("tier")
    signals = []
    followers = c.get("followers") or 0
    reach = c.get("reach")  # median views per follower
    if reach is not None and tier and platform in TYPICAL_REACH and followers >= 3000:
        typical = TYPICAL_REACH[platform][tier]
        ratio = reach / typical
        if ratio < 0.25:
            signals.append(_signal("warn", f"Only {reach:.0%} of followers watch a typical post (typical: about {typical:.0%}). "
                                           "Many followers may be inactive or bought.", 30))
        elif ratio < 0.5:
            signals.append(_signal("warn", f"Fewer followers than usual watch: {reach:.0%} per post vs about {typical:.0%} typical.", 12))
        elif ratio >= 1.5:
            signals.append(_signal("good", f"{reach:.0%} of followers watch a typical post, well above the {typical:.0%} typical for their size.", bonus=10))
    rate = c.get("engagement_rate")
    if rate is not None and tier and platform in TYPICAL_RATE:
        typical = TYPICAL_RATE[platform][tier]
        if rate / typical > 3.5 and (c.get("avg_views") or 0) >= 500:
            signals.append(_signal("warn", f"Likes per view are {rate / typical:.1f}× typical: unusually high, possibly bought likes.", 15))
    likes, comments = c.get("avg_likes"), c.get("avg_comments")
    if likes and likes >= 200 and comments is not None and comments / likes < 0.004:
        signals.append(_signal("warn", f"About {likes:,} likes but only {comments} comments per post: very few people talk back.", 12))

    a = c.get("audience") or {}
    n = a.get("sampled") or 0
    if n >= 15:
        if a["generic_share"] >= 0.6:
            signals.append(_signal("warn", f"{a['generic_share']:.0%} of sampled comments are generic (emoji, \"nice video\").", 20))
        elif a["generic_share"] >= 0.4:
            signals.append(_signal("warn", f"{a['generic_share']:.0%} of sampled comments are generic (emoji, \"nice video\").", 8))
        if a["duplicate_share"] >= 0.15:
            signals.append(_signal("warn", f"The same comment text appears repeatedly ({a['duplicate_share']:.0%} of the sample).", 15))
        if a.get("unique_authors") is not None and a["unique_authors"] < 0.6:
            signals.append(_signal("warn", "A few accounts write most of the comments.", 10))
        if a["spam_share"] >= 0.1:
            signals.append(_signal("warn", f"{a['spam_share']:.0%} of comments are spam (links, \"sub4sub\").", 10))
        if a["question_share"] >= 0.12:
            signals.append(_signal("good", f"Viewers ask them questions ({a['question_share']:.0%} of comments)"
                                           + (", including for buying advice." if a.get("advice_share", 0) >= 0.03 else "."), bonus=5))
        if a["generic_share"] < 0.25 and a["duplicate_share"] < 0.05:
            signals.append(_signal("good", "Comments are real conversation, not emoji or copy-paste.", bonus=10))

    with_likes = sum(1 for p in c.get("recent_posts", []) if isinstance(p.get("likes"), (int, float)))
    points = (2 if n >= 30 else 1 if n >= 10 else 0) + (1 if with_likes >= 5 else 0) + (1 if reach is not None else 0)
    confidence = "high" if points >= 3 else "medium" if points >= 2 else "low"
    score = NEUTRAL + sum(s["bonus"] for s in signals) - sum(s["penalty"] for s in signals)
    score = max(0, min(CAP[confidence], score))
    return {"score": score, "signals": signals, "confidence": confidence}


# --- Sponsorship ------------------------------------------------------------------------------

DISCLOSURE = re.compile(
    r"#ad\b|#sponsored|#spons\b|#mainos|kaupallinen yhteistyö|yhteistyössä|#reklam|i samarbete med|sponsrad|annons\b|"
    r"#reklame|i samarbeid med|sponset|sponsoreret|i samarbejde med|#werbung|#anzeige|gesponsert|in kooperation mit|"
    r"#advertentie|gesponsord|in samenwerking met|#pub\b|#publicité|sponsorisé|en partenariat avec|#publi\b|patrocinado|"
    r"en colaboración con|#adv\b|sponsorizzato|in collaborazione con|#reklama|materiał sponsorowany|sponsorowany|"
    r"sponzorováno|szponzorált|sponsored by|paid partnership|thanks to \w+ for sponsoring|this video is sponsored",
    re.I)
CODE = re.compile(r"\b(use|käytä|koodi|code|kod|rabattcode|rabattkod|gutschein|kupon|codice|código|kód)\b[\s:]*"
                  r"[\"'“]?[A-Z0-9]{3,}\b|\bpromo ?code\b|\bdiscount code\b|\baffiliate\b", re.I)


def sponsorship(c: dict) -> dict:
    """How often recent posts carry a disclosed ad or a discount code."""
    posts = c.get("recent_posts", [])[:15]
    checked = [p for p in posts if (p.get("title") or p.get("desc"))]
    sponsored = [p for p in checked if DISCLOSURE.search(f"{p.get('title') or ''} {p.get('desc') or ''}")]
    codes = [p for p in checked if CODE.search(f"{p.get('title') or ''} {p.get('desc') or ''}")]
    return {
        "checked": len(checked),
        "sponsored": len(sponsored),
        "with_codes": len(codes),
        "posts": [{"title": p.get("title", "")[:90], "url": p.get("url")} for p in (sponsored or codes)[:3]],
    }


# --- Price ------------------------------------------------------------------------------------

# Rough cost per 1,000 views of one sponsored post (EUR), from common creator rate cards.
CPM = {"youtube": (15, 30), "tiktok": (8, 18), "instagram": (8, 18)}
FLOOR = 50  # the smallest creators often take a free product, or a small fee


def _nice(n: float) -> int:
    step = 10 if n < 200 else 50 if n < 1000 else 100 if n < 5000 else 500
    return int(round(n / step) * step) or step


def price_estimate(c: dict) -> dict | None:
    views = c.get("median_views") or c.get("avg_views")
    if not views or c["platform"] == "twitch":  # Twitch deals are priced on live viewers, which we don't have
        return None
    lo, hi = CPM.get(c["platform"], CPM["tiktok"])
    low, high = max(FLOOR, views / 1000 * lo), max(FLOOR * 2, views / 1000 * hi)
    return {"low": _nice(low), "high": _nice(high)}


def assess(c: dict) -> dict:
    """Fill in audience, authenticity, sponsorship and price on a creator (mutates and returns it)."""
    if c.get("comment_sample"):
        c["audience"] = analyze_comments(c["comment_sample"])
    c["authenticity"] = authenticity(c)
    c["sponsorship"] = sponsorship(c)
    c["price"] = price_estimate(c)
    c["assessed_v"] = VERSION
    return c
