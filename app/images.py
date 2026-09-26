"""Download creator images once and serve them locally.

TikTok and Instagram CDN links are signed and expire within days (and often block hotlinking),
so a demo that relies on them breaks. Everything shown in the UI comes from /img instead.
"""
import asyncio
import hashlib
import io

import httpx
from PIL import Image, ImageOps

from .config import IMG_DIR

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "image/avif": ".avif"}

# Covers show at most ~250px wide (x2 for sharp screens). Originals were ~230 KB on average, some 2 MB,
# so a page of 30 cards pulled ~7 MB; as small WebP thumbnails it's a few hundred KB.
THUMB_SIZE = (480, 640)


def shrink(data: bytes) -> bytes | None:
    """A small WebP thumbnail of an image, or None if Pillow can't read it."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            background = Image.new("RGB", img.size, (24, 24, 30))
            background.paste(img, mask=img.getchannel("A"))
            img = background
        else:
            img = img.convert("RGB")
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, "WEBP", quality=80, method=4)
        return out.getvalue()
    except Exception:
        return None


async def cache_image(http: httpx.AsyncClient, url: str | None, sem: asyncio.Semaphore) -> str | None:
    if not url:
        return None
    stem = hashlib.sha1(url.encode()).hexdigest()[:20]
    existing = next(IMG_DIR.glob(stem + ".*"), None)
    if existing:
        return f"/img/{existing.name}"
    async with sem:
        try:
            r = await http.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": UA})
        except httpx.HTTPError:
            return None
    ctype = r.headers.get("content-type", "").split(";")[0].strip()
    if r.status_code != 200 or not ctype.startswith("image/"):
        return None
    small = shrink(r.content)
    path = IMG_DIR / (stem + (".webp" if small else EXT.get(ctype, ".jpg")))
    path.write_bytes(small or r.content)
    return f"/img/{path.name}"


async def cache_creator_images(http: httpx.AsyncClient, creator: dict, sem: asyncio.Semaphore) -> None:
    posts = creator.get("recent_posts", [])[:6]
    # YouTube thumbnails are permanent public URLs; only mirror the expiring ones.
    mirror_posts = creator["platform"] != "youtube"
    results = await asyncio.gather(
        cache_image(http, creator.get("avatar_src"), sem),
        cache_image(http, creator.get("cover_src"), sem),
        *(cache_image(http, p.get("thumb_src"), sem) if mirror_posts else asyncio.sleep(0, result=None) for p in posts),
    )
    creator["avatar"] = results[0] or creator.get("avatar_src")
    creator["cover"] = results[1] or creator["avatar"]
    for post, local in zip(posts, results[2:]):
        post["thumb"] = local or post.get("thumb_src")
    for post in creator.get("recent_posts", [])[6:]:
        post["thumb"] = post.get("thumb_src")
