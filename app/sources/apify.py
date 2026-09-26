"""Thin client for running Apify scraper actors synchronously."""
import httpx

from .. import settings


class ApifyError(Exception):
    pass


async def run_actor(http: httpx.AsyncClient, actor: str, payload: dict, max_items: int, timeout_s: int = 240) -> list[dict]:
    """Run an actor and return its dataset items (blocks until the run finishes).

    max_items caps what a pay-per-result actor can charge for this run.
    Apify answers 408 if a sync run passes 300s, so timeout_s stays below that.
    """
    url = f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
    try:
        r = await http.post(
            url,
            params={"timeout": timeout_s, "clean": "true", "maxItems": max_items},
            headers={"Authorization": f"Bearer {settings.apify_token()}"},
            json=payload,
            timeout=timeout_s + 30,
        )
    except httpx.TimeoutException as e:
        raise ApifyError(f"{actor} timed out") from e
    if r.status_code == 402:
        raise ApifyError("Apify says payment required: check the Apify token in Settings, or your remaining Apify credit")
    if r.status_code == 408:
        raise ApifyError(f"{actor} took longer than Apify's 5-minute limit")
    if r.status_code >= 400:
        raise ApifyError(f"{actor} failed ({r.status_code}): {r.text[:300]}")
    data = r.json()
    if not isinstance(data, list):
        return []
    # Actors report per-item failures inline; drop those.
    return [item for item in data if isinstance(item, dict) and not item.get("error")]
