# Scout: find the creators other tools miss

Scout automates influencer discovery for brands like Prenew, with a focus on micro and mid-size creators
(roughly 1k–250k followers) who don't show up in the big influencer databases.

**How it works (one search):**

1. **Plan.** The AI turns the company brief into search terms and hashtags in each market's own language
   (for example Finnish slang for Finland, German for Germany). This is how it works for small markets too.
   Plans are remembered, so repeating a search needs no AI; with no AI at all, templates are used.
2. **Source.** YouTube (official Data API) and TikTok (Scout's own scraper, free, no key) are searched in
   parallel. TikTok's own search needs a login and shows a CAPTCHA to
   automated browsers, so Scout finds TikTok accounts through web search (Bing, Yahoo, DuckDuckGo) with the
   local-language queries, reads each account's public profile, latest videos and a few video pages
   (views, likes, comments, and the country and language TikTok detected), then follows the @mentions
   in those videos to other local creators.
   An optional **AI web scout** lets Claude search forums, local creator lists and press for creators that
   hashtags miss. It's off by default: it runs paid web searches (about $1–3 per market).
3. **Filter.** Keeps only creators inside the follower range who posted in the last 4 months, then ranks them
   by engagement *relative to accounts of the same size* (a 5k account with 8% engagement beats a 200k account with 1%).
4. **Score, in two steps.** First a **quick score** for everyone, free and instant, from rules: the games
   and niche in their post titles, the country and language the platform reports, gambling flags, engagement
   and activity. Then the **search AI** reads the posts of the most promising ones (12 per search on a local
   model, 40 on a cloud AI) and re-scores niche fit, market fit and brand safety, with a one-line summary,
   reasons, red flags and competitor sponsorships. *Check more with AI* does the next ones. The final **match score** is
   40% niche + 20% market + 25% engagement + 10% activity + 5% safety, minus 15 each for a competitor
   sponsorship, brand-safety concerns or content unrelated to the niche.
   Small, highly engaged, on-niche creators get a 💎 **Hidden gem** badge.
5. **Act.** Shortlist, see contact details, and download **Excel or CSV** of any result set
   (plus an optional drafted first message in the creator's language).

**Downloads use Prenew's own tracker layout.** The first 12 columns match their collaboration sheet exactly
(Creator key, Market, Country, Creator / channel, Agency, Year-week, Platform, Niche / content,
YT subscribers, YT views / video, TikTok followers, TikTok views / video), so rows paste straight in.
One row per creator: when a YouTube channel links to its TikTok (or the other way round), Scout fetches the
other profile after the search and puts both platforms' numbers side by side. *Agency* is a guess from the
contact details (a company email that isn't the creator's own, or management in the bio). Contacts, links,
match score, risks and trend follow in extra columns; a second sheet explains every column.

**Past collaborations.** In *Edit company*, upload the collaboration tracker (Excel or CSV). Scout then
marks creators you've already worked with 🤝, fills *Agency* and *Year-week* for them in downloads, and
shows the AI the past partners as examples of what fits (niche, size, market, platform).

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
   - **Search AI** (runs many times per search): **Local AI** is free and runs on this computer through
     [Ollama](https://ollama.com/download). Scout looks at the computer (memory, graphics card), recommends a
     model (for example `qwen3.5:4b` on a laptop without a graphics card) and downloads it with one button.
     Claude, OpenAI, Gemini, OpenRouter or any OpenAI-compatible API work too, but cost money per search.
   - **Writing AI** (optional, only when you click): drafts outreach messages in the creator's language and
     runs the AI web scout. A paid AI like Claude writes better Finnish or German; a message costs about a cent.
   - **YouTube**: Google Cloud console, then enable *YouTube Data API v3*, then Credentials, then *Create API key* (free, 10k units/day)
   - **TikTok** needs nothing: Scout scrapes TikTok's public pages itself.

   Changes apply immediately. Keys are stored in `data/settings.json` on this computer.

   **Gemini free tier:** quotas are small and per model. When one model's quota runs out (or Google is
   overloaded), Scout switches to a lighter Gemini model by itself and says so in the progress bar.
   Creators that still can't be scored get a *Retry scoring* button. For a demo, enable billing on the
   Google AI Studio project (Flash-Lite costs cents per search) or use Claude/OpenAI.
   Keys in `.env` still work as a fallback.

Check everything from the command line with `.venv/Scripts/python scripts/check_keys.py`.

## Cost and limits for one search (2 markets, YouTube + TikTok)

- YouTube: about 1,000 of the 10,000 free daily quota units (4 searches of 100 units per market + cheap channel/video calls)
- TikTok: free. About 1 minute per market (web searches, then a few public TikTok pages per creator, 4 at a time).
- AI: **nothing with the Local AI.** On a laptop CPU the AI check takes about 1–2 minutes per 4 creators;
  quick scores appear at once, so the grid fills before the AI is done. A cloud AI is faster but costs per
  search. Claude is only called when you draft a message or turn on the web scout.
- Time: 2–4 minutes to quick scores, plus the AI check. **Stop** ends a search early and keeps what was
  already ranked.

## Demo flow (5 minutes)

1. **Problem (30s).** Manual scrolling doesn't scale across markets and languages, and it misses small creators.
2. **Search area (30s).** Click a suggested creator type (for example *Budget gaming*) and show Finland + Germany as markets.
3. **Library (1m).** The grid shows ranked creators. Hover for the summary and tags. Filter *Micro*, sort *Hidden gems first*.
4. **Creator detail (1m).** Show the score breakdown, "why they fit", engagement vs. typical, recent posts,
   and email. Press *Draft a message in Finnish*, then *Show English*.
5. **Live search (1m).** Pick YouTube + Finland and press *Find new creators*. Show the local-language plan and
   progress, with cards landing as NEW.
6. **Another company (30s).** *Add a company* with just a description; Claude suggests creator types for it.
7. **Shortlist + Excel (30s).** Same columns as Prenew's own collaboration tracker, YouTube and TikTok in one row.

Run a full Prenew search (Finland + Germany, all platforms) **before** the pitch so the library is full.

## Project layout

```
app/main.py        HTTP API + serves the UI
app/pipeline.py    one discovery run: plan, source, filter, score
app/llm.py         AI prompts (planning, scoring, pitch, tags, web scout); local models (Ollama), Claude SDK or any OpenAI-compatible API
app/rules.py       free quick scores without AI (games, niche, market, safety) and search templates
app/localai.py     looks at this computer, recommends a local model and downloads it through Ollama
app/settings.py    Settings screen storage: chosen AI, keys (data/settings.json, .env fallback)
app/metrics.py     engagement vs size-typical benchmarks, activity, email extraction, agency guess
app/export.py      Excel/CSV downloads in Prenew's tracker layout (one row per creator)
app/linking.py     links one person's YouTube/TikTok/Instagram profiles (only when one links to the other)
app/partners.py    imports a collaboration tracker; flags past partners
app/sources/       youtube.py (Data API), tiktok.py (own scraper) + websearch.py
app/store.py       JSON-file database (data/db.json)
static/            the UI (plain HTML/CSS/JS, no build step)
scripts/dev_fixture.py   SAMPLE data for UI work without keys (data-dev/, never demo it)
```
