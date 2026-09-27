"""Contact details beyond the bio: the creator's link page (Linktree, Beacons, solo.to...), their own website and
the links on their YouTube channel page. Only public pages, one request each (two for a website without an email on
its front page), a few at a time, and only for creators whose bio showed no email.

Addresses that point inside a network (localhost, 10.x, 169.254.x...) are never fetched: a bio link is written
by a stranger.
"""
import asyncio
import html as htmllib
import ipaddress
import logging
import re
import socket
import urllib.parse

import httpx

from . import metrics

log = logging.getLogger("scout")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
YT_COOKIES = {"CONSENT": "YES+cb", "SOCS": "CAI"}  # skips YouTube's EU consent page

# Link-in-bio services: a page of the creator's links, often with a mailto or a "Business" email.
LINK_PAGES = ("linktr.ee", "beacons.ai", "beacons.page", "solo.to", "lnk.bio", "bio.link", "linkin.bio", "carrd.co",
              "taplink.cc", "taplink.at", "allmylinks.com", "komi.io", "msha.ke", "snipfeed.co", "stan.store",
              "campsite.bio", "hoo.be", "tap.bio", "linkr.bio", "direct.me", "many.link", "heylink.me", "linkfly.to",
              "bio.site", "biolinky.co", "pillar.io", "linkpop.com", "flow.page", "contactinbio.com", "lynk.id",
              "linkbio.co", "shor.by", "fanlink.to", "linkme.bio", "linkin.gg", "guns.lol", "e-z.bio")
# Links that aren't the creator's own site: platforms, shops, payment, sponsors' stores...
NOT_OWN = re.compile(r"(^|\.)(youtube\.com|youtu\.be|tiktok\.com|instagram\.com|twitch\.tv|twitter\.com|x\.com|"
                     r"facebook\.com|fb\.com|discord\.gg|discord\.com|kick\.com|patreon\.com|paypal\.\w+|amazon\.\w+|"
                     r"amzn\.to|spotify\.com|apple\.com|google\.\w+|streamlabs\.com|streamelements\.com|ko-fi\.com|"
                     r"buymeacoffee\.com|snapchat\.com|reddit\.com|steamcommunity\.com|steampowered\.com|epicgames\.com|"
                     r"roblox\.com|minecraft\.net|linkedin\.com|threads\.net|whatsapp\.com|t\.me|bit\.ly|tinyurl\.com|"
                     r"spreadshirt\.\w+|teespring\.com|fourthwall\.com|shopify\.com|etsy\.com|ebay\.\w+|gofundme\.com|"
                     r"tipeee\.com|streamdps\.com|throne\.com|wishlist\.\w+|linkmix\.co|gamma\.app)$", re.I)
# Addresses that belong to the link service or a website builder, not to the creator.
SERVICE_EMAIL = re.compile(r"@(linktr\.ee|linktree\.com|beacons\.ai|solo\.to|carrd\.co|komi\.io|stan\.store|wix\.com|"
                           r"wixpress\.com|squarespace\.com|godaddy\.com|wordpress\.com|sentry\.io|cloudflare\.com|"
                           r"example\.com|domain\.com|email\.com|yourdomain\.\w+|company\.com)$", re.I)
SERVICE_HANDLES = re.compile(r"linktree|beacons|solo\.?to|carrd|komi|stan\.?store|taplink|lnkbio|biolink|allmylinks", re.I)
CF_EMAIL = re.compile(r'data-cfemail="([0-9a-fA-F]{6,})"')
CONTACT_LINK = re.compile(r'href="([^"#]+)"[^>]*>[^<]{0,40}\b(contact|kontakt|yhteys\w*|yhteydenotto|business|'
                          r"impressum|contatti|contacto|kapcsolat)\b", re.I)
YT_LINK = re.compile(r'"channelExternalLinkViewModel":\{"title":\{"content":"[^"]*"\},"link":\{"content":"([^"]+)"')


def host_of(url: str) -> str:
    return (urllib.parse.urlsplit(url if "//" in url else "https://" + url).hostname or "").lower().removeprefix("www.")


def _link_page(url: str) -> bool:
    host = host_of(url)
    return any(host == h or host.endswith("." + h) for h in LINK_PAGES)


def _own_site(url: str, c: dict) -> bool:
    """A website that's probably the creator's own: its name is in the domain (kakkuh.fi for @kakkuh)."""
    host = host_of(url)
    if not host or NOT_OWN.search(host) or _link_page(url):
        return False
    label = re.sub(r"[^a-z0-9]", "", host.split(".")[-2] if host.count(".") >= 1 else host)
    names = {re.sub(r"[^a-z0-9]", "", (c.get(k) or "").lower()) for k in ("handle", "name")}
    return any(len(n) >= 4 and len(label) >= 4 and (n in label or label in n) for n in names)


async def _public(host: str) -> bool:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        return False
    for *_, addr in infos:
        ip = ipaddress.ip_address(addr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


async def fetch(http: httpx.AsyncClient, url: str, max_bytes: int = 700_000) -> str | None:
    """The HTML of a public page (redirects followed and each address checked), or None."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    cookies = YT_COOKIES if host_of(url).endswith("youtube.com") else None
    for _ in range(4):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or not await _public(parts.hostname):
            return None
        try:
            async with http.stream("GET", url, headers=HEADERS, cookies=cookies, timeout=12, follow_redirects=False) as r:
                if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                    url = urllib.parse.urljoin(url, r.headers["location"])
                    continue
                if r.status_code != 200 or "html" not in r.headers.get("content-type", "html"):
                    return None
                body = bytearray()
                async for chunk in r.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        break
                return body.decode(r.encoding or "utf-8", "ignore")
        except (httpx.HTTPError, UnicodeError, ValueError) as e:
            log.info("contact page %s failed: %s", url, e)
            return None
    return None


def _cf_decode(hexstr: str) -> str:
    """Cloudflare hides emails on sites it serves as data-cfemail: XOR with the first byte."""
    try:
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except ValueError:
        return ""


def extract(page: str) -> dict:
    """Emails and profile links on a page."""
    text = htmllib.unescape(page)
    text = text.replace("\\u0040", "@").replace("\\/", "/").replace("[at]", "@").replace("(at)", "@")
    mailtos = [urllib.parse.unquote(m) for m in re.findall(r"mailto:([^\"'?\s<>\\]+)", text, re.I)]
    hidden = [_cf_decode(h) for h in CF_EMAIL.findall(page)]
    emails = [e for e in metrics.extract_emails(" ".join(mailtos), " ".join(hidden), text) if not SERVICE_EMAIL.search(e)]
    socials = {k: v for k, v in metrics.extract_socials("", text).items() if not SERVICE_HANDLES.search(v.rsplit("/", 1)[-1])}
    return {"emails": emails, "socials": socials}


async def youtube_links(http: httpx.AsyncClient, c: dict) -> list[str]:
    """The links a channel shows on its About page (not in the Data API): website, Instagram, link page..."""
    handle = c.get("handle") or ""
    url = f"https://www.youtube.com/{handle}/about" if handle.startswith("@") else (c.get("url") or "").rstrip("/") + "/about"
    page = await fetch(http, url, max_bytes=4_000_000)
    links = YT_LINK.findall(page or "")
    return [l if l.startswith("http") else "https://" + l for l in dict.fromkeys(links)]


def _add(c: dict, found: dict, source: str) -> int:
    """Merge what a page gave; returns how many new emails."""
    have = c.setdefault("emails", [])
    new = [e for e in found["emails"] if e not in have]
    for e in new:
        have.append(e)
        c.setdefault("email_sources", {})[e] = source
    socials = c.setdefault("socials", {})
    for net, url in found["socials"].items():
        if net != c["platform"]:
            socials.setdefault(net, url)
    return len(new)


async def enrich(http: httpx.AsyncClient, c: dict) -> int:
    """Look for an email (and other profiles) beyond the bio. Returns the number of emails added."""
    if c.get("emails"):
        return 0
    links = list(c.get("links") or [])
    if c.get("bio_link"):
        links.insert(0, c["bio_link"])
    if c["platform"] == "youtube":
        about = await youtube_links(http, c)
        c["about_links"] = about[:10]
        links += about
        for url in about:  # their Instagram or TikTok, even when there's no email to find
            for net, pattern in metrics.SOCIAL_PATTERNS.items():
                m = pattern.search(url if url.startswith("http") else "https://" + url)
                if m and net != "youtube":
                    c.setdefault("socials", {}).setdefault(net, m.group(0).rstrip("/.,;"))
    pages = [u for u in dict.fromkeys(links) if _link_page(u)][:2] + [u for u in dict.fromkeys(links) if _own_site(u, c)][:1]
    added = 0
    for url in pages:
        page = await fetch(http, url)
        if not page:
            continue
        added += _add(c, extract(page), host_of(url) + urllib.parse.urlsplit(url).path.rstrip("/"))
        if not added and _own_site(url, c):  # a website's email is usually on its contact page
            m = CONTACT_LINK.search(page)
            if m:
                contact = urllib.parse.urljoin(url if url.startswith("http") else "https://" + url, m.group(1))
                if host_of(contact) == host_of(url):
                    sub = await fetch(http, contact)
                    if sub:
                        added += _add(c, extract(sub), host_of(contact) + urllib.parse.urlsplit(contact).path.rstrip("/"))
        if added:
            break
    c["contacts_checked"] = True
    return added


async def enrich_many(http: httpx.AsyncClient, creators: list[dict], concurrency: int = 6) -> int:
    """enrich() for everyone without an email, a few at a time. Returns how many creators gained an email."""
    sem = asyncio.Semaphore(concurrency)

    async def one(c):
        async with sem:
            try:
                return 1 if await enrich(http, c) else 0
            except Exception as e:  # extra detail only; never fail a search over it
                log.info("contacts for %s failed: %s", c.get("id"), e)
                return 0

    return sum(await asyncio.gather(*(one(c) for c in creators if not c.get("emails"))))
