"""Write a clearly-labelled SAMPLE dataset to data-dev/ for UI work without API keys.

Usage:  python scripts/dev_fixture.py
        set SCOUT_DATA=data-dev && python -m uvicorn app.main:app --port 8001
Never demo this data: every creator is named "Sample creator N".
"""
import copy
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import audience, metrics, rules, scoring  # noqa: E402
from app.pipeline import build_match, merge_ai  # noqa: E402
from app.store import PRENEW  # noqa: E402

OUT = ROOT / "data-dev"
IMG = OUT / "img"
IMG.mkdir(parents=True, exist_ok=True)
random.seed(7)

TOPICS = ["minecraft survival", "fortnite", "budget gaming pc build", "cs2 ranked", "gta rp", "roblox obby",
          "gpu review", "desk setup tour", "valorant clips", "ark survival"]
PLATFORMS = ["youtube", "tiktok", "youtube"]
COMMENTS = {
    "fi": ["Mikä näytönohjain tossa on?", "Tosi hyvä video taas!", "Kannattaako tää kone ostaa vai odottaa?",
           "Mä ostin just samanlaisen koneen", "Hyvä video", "😂😂", "Mitä tää maksoi?", "Ihan paras kanava"],
    "de": ["Welche Grafikkarte ist das?", "Richtig gutes Video wie immer", "Lohnt sich der PC für Fortnite?",
           "Ich habe den gleichen gekauft", "nice", "🔥🔥🔥", "Was kostet der ungefähr?", "Bester Kanal"],
}
GENERIC = ["nice video", "🔥🔥🔥", "first", "wow", "❤️", "nice", "cool"]


def svg_cover(i: int) -> str:
    h = (i * 47) % 360
    path = IMG / f"sample{i}.svg"
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300">'
        f'<rect width="300" height="300" fill="hsl({h},45%,45%)"/>'
        f'<text x="150" y="170" font-family="Arial" font-size="44" font-weight="700" fill="white" text-anchor="middle">S{i}</text></svg>',
        encoding="utf-8",
    )
    return f"/img/{path.name}"


def main():
    now = datetime.now(timezone.utc)
    company = {**copy.deepcopy(PRENEW), "created_at": now.isoformat(), "last_job_id": "job_sample"}
    creators, matches = {}, {}
    for i in range(1, 46):
        platform = PLATFORMS[i % 3]
        followers = random.choice([2400, 5800, 9100, 14000, 23000, 38000, 61000, 120000])
        market = random.choice(["FI", "DE"])
        lang = "fi" if market == "FI" else "de"
        topic = random.choice(TOPICS)
        bought = i % 11 == 0  # a few with suspicious numbers, to show the authenticity signals
        posts = []
        for k in range(10):
            views = int(followers * random.uniform(0.02, 0.06) if bought else followers * random.uniform(0.1, 0.9))
            if k == 3 and i % 4 == 0:
                views *= 8  # one viral hit
            sponsored = k == 1 and i % 3 == 0
            posts.append({
                "title": f"Sample post {k + 1}: {topic if k % 3 else random.choice(TOPICS)}",
                "desc": ("Kaupallinen yhteistyö. Käytä koodia SAMPLE10" if sponsored and lang == "fi"
                         else "#Werbung Rabattcode SAMPLE10" if sponsored else "Sample description."),
                "url": f"https://example.com/sample{i}/post{k + 1}", "thumb": svg_cover((i + k) % 45 + 1),
                "views": views, "likes": int(views * random.uniform(0.02, 0.1) * (4 if bought else 1)),
                "comments": int(views * random.uniform(0.002, 0.01) * (0.1 if bought else 1)),
                "date": (now - timedelta(days=3 + k * random.randint(3, 8))).isoformat(), "is_short": k % 4 == 3,
            })
        cover = svg_cover(i)
        pool = GENERIC * 4 if bought else COMMENTS[lang] * 3 + GENERIC
        c = {
            "id": f"sample_{i}", "platform": platform, "handle": f"@sample{i}", "name": f"Sample creator {i}",
            "url": "https://example.com", "avatar": cover, "cover": cover,
            "bio": "Sample bio." + (" contact: sample@example.com" if i % 3 else ""),
            "bio_link": None, "country": market if i % 5 else "", "language": lang, "followers": followers,
            "posts_count": 120, "verified": False, "recent_posts": posts, "found_via": ["Sample data"],
            "comment_sample": [{"text": t, "author": f"a{random.randint(1, 8 if bought else 400)}"} for t in random.sample(pool, min(len(pool), 30))]
            if platform == "youtube" else [],
        }
        metrics.compute(c)
        audience.assess(c)
        search = {"markets": [market], "tags": ["Minecraft", "Fortnite", "Budget gaming", "PC building"]}
        r = rules.quick_score(c, company, search)
        if i % 3:  # most have a (simulated) AI check, with evidence that cites posts
            r = merge_ai(r, {
                "content_fit": random.randint(55, 95), "audience_fit": random.randint(40, 90),
                "market_fit": random.randint(65, 95), "brand_fit": random.randint(60, 90), "readiness": random.randint(40, 85),
                "brand_safety": 100 if i % 7 else 55,
                "summary": f"Sample summary: {topic} creator for a {market} audience.",
                "evidence": [
                    scoring.evidence_item("content", "+", f"Regularly posts {topic} videos", scoring.cite(posts[1:4]), src="ai", fact=False),
                    scoring.evidence_item("audience", "+" if i % 2 else "-",
                                          "Viewers ask which PC to buy" if i % 2 else "Audience looks mostly under 13",
                                          scoring.cite(posts[:1]), [c["comment_sample"][0]["text"]] if c["comment_sample"] else [],
                                          src="ai", fact=False),
                ],
                "ai_checked": "deep" if i % 8 == 0 else True,
                "verdict": "Sample verdict: worth a test collaboration with a discount code." if i % 8 == 0 else "",
                "collab_idea": "Sample idea: build a budget gaming PC with a refurbished one." if i % 8 == 0 else "",
                "audience_note": "Sample: mostly 15-25, Finnish-speaking." if i % 8 == 0 else "",
            })
        creators[c["id"]] = c
        matches[c["id"]] = build_match(c, r, "job_sample" if i > 38 else "job_old", [market], company)
    jobs = {
        "job_old": {"id": "job_old", "company_id": company["id"], "focus": "", "tags": ["Minecraft", "Fortnite"],
                    "platforms": ["youtube", "tiktok"], "markets": ["FI"], "follower_min": 5000, "follower_max": 250000,
                    "status": "done", "steps": [], "new": 38, "created_at": (now - timedelta(days=2)).isoformat()},
        "job_sample": {"id": "job_sample", "company_id": company["id"], "focus": "budget", "tags": ["Budget gaming"],
                       "platforms": ["youtube"], "markets": ["DE"], "follower_min": 1000, "follower_max": None,
                       "status": "done", "steps": [], "new": 7, "created_at": now.isoformat()},
    }
    db = {"companies": {company["id"]: company}, "creators": creators, "matches": {company["id"]: matches}, "jobs": jobs}
    (OUT / "db.json").write_text(json.dumps(db, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(creators)} sample creators to {OUT}")


if __name__ == "__main__":
    main()
