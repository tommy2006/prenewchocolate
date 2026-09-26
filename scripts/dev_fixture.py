"""Write a clearly-labelled SAMPLE dataset to data-dev/ for UI work without API keys.

Usage:  python scripts/dev_fixture.py
        set SCOUT_DATA=data-dev && python -m uvicorn app.main:app --port 8001
Never demo this data: every creator is named "Sample creator N".
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import metrics  # noqa: E402
from app.pipeline import build_match  # noqa: E402
from app.store import PRENEW  # noqa: E402

OUT = ROOT / "data-dev"
IMG = OUT / "img"
IMG.mkdir(parents=True, exist_ok=True)
random.seed(7)

TAGS = ["PC Building", "Budget Gaming", "Hardware Reviews", "CS2", "Streaming Setup", "Minecraft", "Esports", "Retro Gaming", "Cable Management", "GPU Benchmarks"]
PLATFORMS = ["youtube", "tiktok", "instagram"]


def svg_cover(i: int) -> str:
    h = (i * 47) % 360
    path = IMG / f"sample{i}.svg"
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 400">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl({h},70%,55%)"/>'
        f'<stop offset="1" stop-color="hsl({(h + 60) % 360},70%,30%)"/></linearGradient></defs>'
        f'<rect width="300" height="400" fill="url(#g)"/><circle cx="150" cy="170" r="70" fill="rgba(255,255,255,.25)"/>'
        f'<text x="150" y="360" font-family="Arial" font-size="28" font-weight="700" fill="white" text-anchor="middle">SAMPLE {i}</text></svg>',
        encoding="utf-8",
    )
    return f"/img/{path.name}"


def main():
    now = datetime.now(timezone.utc)
    creators, matches = {}, {}
    for i in range(1, 46):
        platform = PLATFORMS[i % 3]
        followers = random.choice([2400, 5800, 9100, 14000, 23000, 38000, 61000, 120000])
        market = random.choice(["FI", "DE"])
        posts = []
        for k in range(8):
            views = int(followers * random.uniform(0.1, 0.9))
            posts.append({
                "title": f"Sample post {k + 1}: {random.choice(TAGS).lower()} video",
                "url": "https://example.com", "thumb": svg_cover((i + k) % 45 + 1),
                "views": views, "likes": int(views * random.uniform(0.02, 0.1)), "comments": int(views * random.uniform(0.002, 0.01)),
                "date": (now - timedelta(days=3 + k * random.randint(3, 9))).isoformat(), "is_short": k % 4 == 3,
            })
        cover = svg_cover(i)
        c = {
            "id": f"sample_{i}", "platform": platform, "handle": f"@sample{i}", "name": f"Sample creator {i}",
            "url": "https://example.com", "avatar": cover, "cover": cover, "bio": "Sample bio. contact: sample@example.com",
            "bio_link": None, "country": market, "language": "fi" if market == "FI" else "de", "followers": followers,
            "posts_count": 120, "verified": False, "recent_posts": posts, "found_via": ["Sample data"],
        }
        metrics.compute(c)
        tags = random.sample(TAGS, 4)
        r = {
            "niche_fit": random.randint(45, 98), "market_fit": random.randint(60, 98), "brand_safety": random.choice([100, 100, 90, 60]),
            "language": c["language"], "country": market, "summary": f"Sample summary for creator {i}: {tags[0].lower()} content for a {market} audience.",
            "niche": random.choice(["Gaming", "Tech reviews", "PC building"]),
            "games": random.sample(["Valorant", "Counter-Strike 2", "Minecraft", "Fortnite", "EA FC 26"], random.choice([0, 1, 2])),
            "tags": tags, "why": ["Sample reason one", "Sample reason two"], "red_flags": [] if i % 5 else ["Sample red flag"],
            "competitor_sponsor": False,
        }
        creators[c["id"]] = c
        matches[c["id"]] = build_match(c, r, "job_sample" if i > 38 else "job_old", [market])
    company = {**PRENEW, "created_at": now.isoformat(), "last_job_id": "job_sample"}
    db = {"companies": {company["id"]: company}, "creators": creators, "matches": {company["id"]: matches}, "jobs": {}}
    (OUT / "db.json").write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(creators)} sample creators to {OUT}")


if __name__ == "__main__":
    main()
