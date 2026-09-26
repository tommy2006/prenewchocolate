"""Find social profiles through ordinary web search (Bing, Yahoo, DuckDuckGo).

TikTok's own search and hashtag pages need a logged-in browser and show a CAPTCHA to automated ones,
but search engines index TikTok profiles and videos well, in every language. Each engine returns
a few different accounts, so we ask all three and merge.
"""
import asyncio
import base64
import html as htmllib
import logging
import re
import urllib.parse

import httpx

from ..markets import MARKETS

log = logging.getLogger("scout")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
_engines = asyncio.Semaphore(3)  # stay polite: a few requests at a time across all searches

PROFILE_RE = {
    "tiktok": re.compile(r"tiktok\.com/@([\w.\-]{2,30})"),
    "youtube": re.compile(r"youtube\.com/@([\w.\-]{3,30})"),
}
BING_LINK = re.compile(r"[?&](?:amp;)?u=a1([A-Za-z0-9_\-]+)")  # Bing wraps result links as base64
NOT_HANDLES = {"tiktok", "tiktokcreators", "tiktok_uk", "tiktok_us", "discover"}


def _handles(network: str, html: str) -> list[str]:
    # Engines also show the address as text ("tiktok.com › @name", often with tags inside): read that too.
    shown = re.sub(r"\s*›\s*", "/", htmllib.unescape(re.sub(r"<[^>]+>", " ", html)))
    texts = [html, urllib.parse.unquote(urllib.parse.unquote(html)), shown]
    for b in BING_LINK.findall(html):
        try:
            texts.append(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "ignore"))
        except ValueError:
            pass
    found = []
    for text in texts:
        for h in PROFILE_RE[network].findall(text):
            h = h.lower().rstrip(".")
            if h not in found and h not in NOT_HANDLES:
                found.append(h)
    return found


def _locale(market: str) -> tuple[str, str]:
    lang = MARKETS.get(market, {}).get("languages", ["en"])[0]
    return ("uk" if market == "GB" else market.lower()), lang


async def _get(http: httpx.AsyncClient, method: str, url: str, **kw) -> str:
    async with _engines:
        try:
            r = await http.request(method, url, timeout=15, follow_redirects=True, **kw)
        except httpx.HTTPError as e:
            log.info("web search %s failed: %s", url, e)
            return ""
        await asyncio.sleep(0.4)
    return r.text if r.status_code == 200 else ""


async def search(http: httpx.AsyncClient, network: str, query: str, market: str) -> list[str]:
    """Profile handles on `network` that web search finds for `query`, e.g. ("tiktok", "fortnite suomi", "FI")."""
    q = f"site:{network}.com {query}"
    country, lang = _locale(market)
    headers = {"User-Agent": UA, "Accept-Language": f"{lang},{lang}-{market};q=0.9,en;q=0.6"}
    pages = await asyncio.gather(
        _get(http, "GET", "https://www.bing.com/search", params={"q": q}, headers=headers),
        *(_get(http, "GET", "https://search.yahoo.com/search", params={"p": q, "b": b}, headers=headers) for b in (1, 11, 21)),
        _get(http, "POST", "https://html.duckduckgo.com/html/", data={"q": q, "kl": f"{country}-{lang}"}, headers=headers),
    )
    found = []
    for html in pages:
        for h in _handles(network, html):
            if h not in found:
                found.append(h)
    return found
