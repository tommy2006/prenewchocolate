"""Free connectivity checks for the data-source keys (used by the Settings screen and scripts/check_keys.py)."""
import httpx


class CheckError(Exception):
    pass


async def check_youtube(key: str) -> str:
    if not key:
        raise CheckError("No YouTube API key yet")
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get("https://www.googleapis.com/youtube/v3/i18nRegions",  # costs 1 quota unit
                           params={"part": "snippet", "key": key})
    if r.status_code == 200:
        return "YouTube key works"
    try:
        msg = r.json()["error"]["message"]
    except Exception:
        msg = f"error {r.status_code}"
    raise CheckError(f"YouTube: {msg}")
