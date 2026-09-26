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


async def check_apify(token: str) -> str:
    if not token:
        raise CheckError("No Apify token yet")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=20) as http:
        r = await http.get("https://api.apify.com/v2/users/me", headers=headers)
        if r.status_code != 200:
            raise CheckError("Apify rejected the token. Copy it again from console.apify.com > Settings > API & Integrations")
        user = r.json().get("data", {})
        msg = f"Apify works: account '{user.get('username')}'"
        limits = await http.get("https://api.apify.com/v2/users/me/limits", headers=headers)
    if limits.status_code == 200:
        d = limits.json().get("data", {})
        used = d.get("current", {}).get("monthlyUsageUsd")
        cap = d.get("limits", {}).get("maxMonthlyUsageUsd")
        if used is not None and cap:
            msg += f", ${used:.2f} of ${cap:.2f} used this month"
    return msg
