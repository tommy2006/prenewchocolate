# Scout: find the creators other tools miss

Scout automates influencer discovery for brands like Prenew, with a focus on micro and mid-size creators
(roughly 1k–250k followers) who don't show up in the big influencer databases.

**How it works (one search):**

1. **Plan.** Claude turns the company brief into search terms and hashtags in each market's own language
   (for example Finnish slang for Finland, German for Germany). This is how it works for small markets too.
2. **Source.** YouTube (official Data API), TikTok and Instagram (Apify scrapers) are searched in parallel.
   An optional **AI web scout** lets Claude search forums, local creator lists and press for creators that
   hashtags miss.
3. **Filter.** Keeps only creators inside the follower range who posted in the last 4 months, then ranks them
   by engagement *relative to accounts of the same size* (a 5k account with 8% engagement beats a 200k account with 1%).
4. **Score.** Claude reads each creator's bio and recent posts and scores niche fit, market fit and brand safety,
   with a one-line summary, tags, reasons and red flags. The final **match score** is
   40% niche + 20% market + 25% engagement + 10% activity + 5% safety.
   Small, highly engaged, on-niche creators get a 💎 **Hidden gem** badge.
5. **Act.** Shortlist, see contact details, and download **Excel or CSV** of any result set
   (plus an optional drafted first message in the creator's language).

**Data per creator (what Prenew asked for):** country · subscribers/followers · **average views over the last
30 days** (90 days for less active creators; YouTube Shorts and posts under 2 days old are left out) ·
**niche and which games** · contact details (emails from the bio *and* video descriptions, plus their other
profiles like Instagram/Twitch/Discord) · risks and brand safety · **views trend** (last 30 days vs. the 60 before) ·
engagement vs. typical for their size · posting frequency.

Any size can be searched; with no size picked, everything from 1k followers up is included
(Prenew's usual range: YouTube 50k–250k subscribers, TikTok 4k+).

Adding a company only needs a name and a description; Claude suggests creator types from it.
What to look for is picked in the search area: **creator type** tags, **market**, platform and size, plus
(under *More options*) collaboration type, things to avoid and example creators. The same choices filter
the saved creators instantly and drive *Find new creators*, and they're remembered per company.

## Setup (5 minutes)

1. Double-click `run.bat` (or run the command below), then open http://localhost:8000

   ```bash
   .venv/Scripts/python -m uvicorn app.main:app --port 8000
   ```

2. Click the **gear (Settings)** and set up:
   - **AI** (pick one): Claude, OpenAI, Gemini, OpenRouter, Ollama (local and free), or any OpenAI-compatible
     API. Paste its key, press *Load models* and pick one, then *Test*. The optional *AI web scout* needs Claude;
     everything else works with any of them.
   - **YouTube**: Google Cloud console, then enable *YouTube Data API v3*, then Credentials, then *Create API key* (free, 10k units/day)
   - **Apify** (TikTok + Instagram): sign up at https://apify.com, then Settings, then *API & Integrations* (free plan includes $5/month)

   Changes apply immediately. Keys are stored in `data/settings.json` on this computer.

   **Gemini free tier:** quotas are small and per model. When one model's quota runs out (or Google is
   overloaded), Scout switches to a lighter Gemini model by itself and says so in the progress bar.
   Creators that still can't be scored get a *Retry scoring* button. For a demo, enable billing on the
   Google AI Studio project (Flash-Lite costs cents per search) or use Claude/OpenAI.
   Keys in `.env` still work as a fallback.

Check everything from the command line with `.venv/Scripts/python scripts/check_keys.py`.

## Cost and limits for one search (2 markets, 3 platforms)

- YouTube: about 1,000 of the 10,000 free daily quota units (4 searches of 100 units per market + cheap channel/video calls)
- Apify: at most about 800 scraped results, capped with `maxItems` (about $1.50–2.00 on the free plan, so the free $5
  covers 2–3 full searches; test with one market and one platform)
- AI: search planning + about 8 scoring calls for up to 60 creators (cheap models like Gemini Flash or
  GPT mini cost cents; free tiers can hit rate limits, which the app retries)
- Time: 2–4 minutes. Cards appear as batches finish scoring.

## Demo flow (5 minutes)

1. **Problem (30s).** Manual scrolling doesn't scale across markets and languages, and it misses small creators.
2. **Search area (30s).** Click a suggested creator type (for example *Budget gaming*) and show Finland + Germany as markets.
3. **Library (1m).** The grid shows ranked creators. Hover for the summary and tags. Filter *Micro*, sort *Hidden gems first*.
4. **Creator detail (1m).** Show the score breakdown, "why they fit", engagement vs. typical, recent posts,
   and email. Press *Draft a message in Finnish*, then *Show English*.
5. **Live search (1m).** Pick YouTube + Finland and press *Find new creators*. Show the local-language plan and
   progress, with cards landing as NEW.
6. **Another company (30s).** *Add a company* with just a description; Claude suggests creator types for it.
7. **Shortlist + CSV (30s).** Plugs straight into an existing outreach workflow.

Run a full Prenew search (Finland + Germany, all platforms) **before** the pitch so the library is full.

## Project layout

```
app/main.py        HTTP API + serves the UI
app/pipeline.py    one discovery run: plan, source, filter, score
app/llm.py         AI prompts (planning, scoring, pitch, tags, web scout); Claude SDK or any OpenAI-compatible API
app/settings.py    Settings screen storage: chosen AI, keys (data/settings.json, .env fallback)
app/metrics.py     engagement vs size-typical benchmarks, activity, email extraction
app/sources/       youtube.py (Data API), tiktok.py + instagram.py (Apify)
app/store.py       JSON-file database (data/db.json)
static/            the UI (plain HTML/CSS/JS, no build step)
scripts/dev_fixture.py   SAMPLE data for UI work without keys (data-dev/, never demo it)
```
