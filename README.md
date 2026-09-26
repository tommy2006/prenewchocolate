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
   **Twitch** (optional, official API, free Client ID and Secret in *Settings*) is searched by broadcast language:
   streams live right now in the market's language (overall and per game) and channels matching each creator type.
   Twitch shows no likes, comments or past live viewers, so Twitch creators get no price estimate and "views per
   video" are views of their recent past broadcasts. Instagram and Facebook have no search a tool like this may use,
   so they appear only as profiles a creator links to (contacts and the export).
   An optional **AI web scout** lets Claude search forums, local creator lists and press for creators that
   hashtags miss. It's off by default: it runs paid web searches (about $1–3 per market).
3. **Filter.** Keeps only creators inside the follower range who posted in the last 4 months.
4. **Read the audience.** For YouTube creators Scout samples real viewer comments from their latest videos
   (1 quota unit per video): which language viewers write in, whether comments are real conversation or emoji and
   copy-paste, whether viewers ask for advice. Together with views per follower, likes per view and comments per like
   (compared with accounts of the same size), this gives an **authenticity** score with the signals behind it
   ("only 3% of followers watch a typical post", "many likes but almost no comments"). Signals, never "bots detected".
   It starts at a neutral 70 ("nothing suspicious found" isn't proof), rises only with positive evidence, and can't
   get high when there's little data.
5. **Score like a marketer, with evidence.** Two headline numbers instead of one opaque score:
   - **Fit**: would a marketer pick them for this brand? *Content* (matches the creator types), *audience* (viewers
     are the brand's customers: old enough, interested, trusting), *market* (incl. comment language), *brand & safety*
     (tone, gambling, competitor sponsors) and *readiness & cost* (contact, sponsor experience without ad fatigue,
     estimated price vs budget).
   - **Audience quality**: authenticity, engagement vs typical, consistency (how steady views are across the middle
     half of their posts, so one viral hit or flop doesn't distort it), activity and momentum (views trend, on a
     curve: only a doubling gets past 90). Scores of 100 are rare by design: most creators have something to improve.

   Every part comes with **evidence**: short claims that cite the posts (and quote the comments) they're based on.
   The AI must cite post and comment references; a claim citing a post that doesn't exist is dropped. A
   **confidence** level says how much data the scores rest on. Rules score everyone at once for free; the search AI
   re-checks the most promising (12 per search on a laptop model, 40 on a cloud AI, all of them on your own GPU server). **Deep evaluation** (one click,
   uses the writing AI) reads descriptions and up to 30 comments and writes a verdict, who the audience likely is,
   and a collaboration idea. The ranking (**match**) blends Fit and Quality by the brand's campaign goal
   (Sales 65/35, Balanced 60/40, Awareness 50/50). Small, highly engaged, authentic on-niche creators get a **Gem** tag.
6. **Act.** Shortlist (or select several), see contact details and an estimated price per post, draft a first
   message in the creator's language, and download **Excel or CSV**. "Not a fit" asks for a one-tap reason
   (wrong niche, audience too young...); the AI sees those reasons and the shortlist on the next search.

**Downloads use Prenew's own tracker layout.** The first 12 columns match their collaboration sheet exactly
(Creator key, Market, Country, Creator / channel, Agency, Year-week, Platform, Niche / content,
YT subscribers, YT views / video, TikTok followers, TikTok views / video), so rows paste straight in.
One row per creator: when a YouTube channel links to its TikTok (or the other way round), Scout fetches the
other profile after the search and puts both platforms' numbers side by side. *Agency* is a guess from the
contact details (a company email that isn't the creator's own, or management in the bio). Contacts, links,
match score, Fit, Audience quality, confidence, authenticity, estimated price, risks, trend and the verdict follow in
extra columns; a second sheet explains every column.

**Past collaborations.** In *Brand profile* (company menu), upload the collaboration tracker (Excel or CSV). Scout then
tags creators you've already worked with as *Past partner*, fills *Agency* and *Year-week* for them in downloads, and
shows the AI the past partners as examples of what fits (niche, size, market, platform). Then:

- **Look up & complete** finds each creator of the tracker on YouTube and TikTok by name (the handles the name suggests,
  then a web search), adds them to the results and scores them. A profile only counts if its size is close to the
  tracker's numbers; with no numbers, the name must be distinctive and the profile in the right market ("Noah" won't
  match a random big account). **Completed tracker** hands the sheet back row for row with the empty cells filled
  (highlighted; nothing you typed changes), plus current numbers, links, email, Fit and Audience quality.
- **Check against your history** (same window) shows how many past partners Scout's *own searches* found and where they
  rank (looking them up doesn't count), and how Scout scores the partners it looked up, lowest first, with their
  weakest part. They were picked by the brand, so a low score shows where the scoring may be missing something.
- **Find more like these** searches the creators that your past partners @mention in their videos or feature on their
  channel: usually local creators in the same niche. The same button is in *More filters* for *Creators you already
  like*, and every creator window has **Find more like this**.

**Data per creator (what Prenew asked for):** country · subscribers/followers · **average and median views over the
last 30 days** (90 days for less active creators; YouTube Shorts and posts under 2 days old are left out) ·
**niche and which games** · contact details (emails from the bio *and* video descriptions, plus their other
profiles like Instagram/Twitch/Discord) · risks and brand safety · **views trend** (last 30 days vs. the 60 before) ·
engagement vs. typical for their size · posting frequency · consistency · **authenticity signals** · comment
languages · sponsored posts and discount codes · **estimated price per post**.

Any size can be searched; with no size picked, everything from 1k followers up is included.
**The company's usual size** is set per platform in *Brand profile* (Prenew: YouTube 50k–250k subscribers,
TikTok 4k+). Pick *Prenew's usual* under *Size* and both the list and new searches use each platform's own range.
*More filters → Typical views per post* narrows by median views (for example 20k–100k).

**Brand profile.** The AI judges fit against the company's profile: what it sells, the **target customer**,
youngest audience age, price range, **competitors** (creators they sponsor are flagged), values and tone, never-work-with
list, **budget per collaboration** (compared with each creator's estimated price) and **campaign goal**. Only the name
and description are required; *Fill from website* drafts the rest. Changing the goal or budget re-ranks everyone.
With a collaboration tracker imported, the profile shows a **check against your history**: how many past partners
Scout found and where they rank.

**Two looks.** *Modern* (the default): clean and white, bold type, orange buttons and big rounded creator images.
*Classic*: the playful original with the comic font and poster cards. Switch with *Modern | Classic* in the top bar;
everything else works the same in both, and both follow your computer's light or dark mode.

**Searching.** Type what you want in plain words, e.g. *Finnish CS2 YouTubers under 50k with email*, and press
Enter: markets, platform, creator types, size and "has email" are filled in instantly by rules, and the AI reads
whatever the rules didn't understand. The filters stay visible and editable; *Undo* puts them back. Click the empty
search box for **recent searches**. Creators show as **posters** (their image, with Fit and Quality on it and a
summary on hover), or as a compact table. Each score sits in a **ring that fills up to it** (on the Modern cards, stacked in the bottom-left corner of the picture) (green, amber or grey; a dashed ring is a
quick estimate the AI hasn't checked yet). **Hover any score** for a short explanation about that creator (what
helps, what hurts, what isn't checked yet). Click a creator to open a window with their image and a **summary**
(verdict, Fit and Quality in plain words, key numbers, why they could work, what to watch out for, contact) and
their **recent videos**: click one to watch it right there (YouTube and TikTok). The evidence, audience details,
all numbers and the first message are in sections you open when you need them. **Click a creator's name**
(underlined, with a small chart icon) for their **stats window**: followers, typical views, engagement, trend, posting
rate and price at a glance, a chart of views and of engagement per recent post against their typical level (hover a
column for that post), audience authenticity, comment languages, sponsorship history, and every post as a table. Keyboard: ↑/↓ move
(also inside the window), Enter open, s shortlist, x select, h not a fit, / search, Esc close.

## Setup (5 minutes)

1. Start Scout, then open http://localhost:8001
   - **Windows:** double-click `run.bat`.
   - **Mac / Linux:** in Terminal, in the project folder: `./run.sh`

   The first start installs what Scout needs (a few minutes). Stop Scout with Ctrl+C in that window.
   Another port: `PORT=8002 ./run.sh`.

2. Click the **gear (Settings)** and set up:
   - **Search AI** (runs many times per search): **Local AI** is free and runs on this computer through
     [Ollama](https://ollama.com/download). Scout looks at the computer (memory, graphics card), recommends a
     model (for example `qwen3.5:4b` on a laptop without a graphics card) and downloads it with one button.
     **Your GPU server** runs a large open model on your own machine (for example a Verda instance with 2× H200):
     no cost per search, so the AI checks *every* creator, several at a time. See *Your own GPU server* below.
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

### Your own GPU server (Verda or any Linux GPU machine)

`scripts/verda_setup.sh` turns a GPU server into Scout's AI: it installs [vLLM](https://docs.vllm.ai), downloads a
model that fits (2× H200: *Qwen3-235B-A22B-Instruct-2507 FP8*, strong in Finnish, German and Swedish; smaller
servers: *Qwen3-30B-A3B-Instruct-2507*), and runs it as a service with an API key that restarts by itself, also
after a spot instance comes back. From your computer:

```bash
scp scripts/verda_setup.sh root@SERVER-IP:
ssh root@SERVER-IP 'bash verda_setup.sh'
```

The first run takes 20–40 minutes (mostly the model download, kept for next time). At the end it prints the
**address** and **API key**: paste them in Settings → *Your GPU server* (model `scout`), choose it as the search AI
and the writing AI, and Save. The address is plain HTTP protected by the key; for an encrypted connection run
`PUBLIC=0 bash verda_setup.sh` and use an SSH tunnel (`ssh -N -L 8000:localhost:8000 root@SERVER-IP`, address
`http://localhost:8000/v1`). If the address doesn't answer, open TCP port 8000 in the server's firewall.
Other options: `MODEL=org/name` for another Hugging Face model, `PORT=...`. The optional AI web scout still needs Claude.

Check everything from the command line with `.venv/Scripts/python scripts/check_keys.py`.

## Cost and limits for one search (2 markets, YouTube + TikTok)

- YouTube: about 1,000 of the 10,000 free daily quota units (4 searches of 100 units per market + cheap channel/video
  calls, + 2 units per YouTube creator for the comment sample)
- TikTok: free. About 1 minute per market (web searches, then a few public TikTok pages per creator, 4 at a time).
- AI: **nothing with the Local AI.** On a laptop CPU the AI check takes about 1–2 minutes per 4 creators;
  quick scores appear at once, so the grid fills before the AI is done. A cloud AI is faster but costs per
  search. Claude is only called when you draft a message or turn on the web scout.
- Time: 2–4 minutes to quick scores, plus the AI check. **Stop** ends a search early and keeps what was
  already ranked.

## Demo flow (5 minutes)

1. **Problem (30s).** Manual scrolling doesn't scale across markets and languages, misses small creators, and
   follower counts say nothing about whether the audience is real or would buy.
2. **Brand profile (30s).** Show Prenew's target customer, competitors, budget and goal: this is what "fit" means.
3. **Search in plain words (30s).** Type *Finnish Minecraft YouTubers under 50k with email*, press Enter, show the
   filters it understood.
4. **Table + panel (1.5m).** Sort by *Best match*. Open a creator: Fit and Audience quality, each part with evidence
   that links to the actual posts and quotes comments; authenticity signals; confidence. Press ↓ to walk the list.
   Show one with a low Quality score and its warning signs.
5. **Deep evaluation + outreach (1m).** *Deep evaluation* on a top creator: verdict, audience, collaboration idea.
   *Draft a message in Finnish*, then *Show English*.
6. **Team feedback (30s).** Mark one *Not a fit → Audience too young*; the next search learns from it.
7. **Live search + Excel (30s).** Press *Find new creators*, show the progress, then download the shortlist in
   Prenew's own tracker layout. With the tracker imported, show the check against past partners.

Run a full Prenew search (Finland + Germany, all platforms) **before** the pitch so the library is full.

## Project layout

```
app/main.py        HTTP API + serves the UI
app/pipeline.py    one discovery run: plan, source, filter, score
app/llm.py         AI prompts (planning, scoring with cited evidence, deep evaluation, search bar, brand profile from a
                   website, pitch, tags, web scout); local models (Ollama), Claude SDK or any OpenAI-compatible API
app/rules.py       free quick scores without AI, with evidence (content, audience, market, brand, readiness) and search templates
app/scoring.py     the match model: Fit and Audience quality, campaign-goal weights, confidence
app/audience.py    comment language and quality, authenticity signals, sponsorship, estimated price
app/query.py       the search bar: plain words -> filters, without AI
app/localai.py     looks at this computer, recommends a local model and downloads it through Ollama
app/settings.py    Settings screen storage: chosen AI, keys (data/settings.json, .env fallback)
app/metrics.py     engagement vs size-typical benchmarks, activity, email extraction, agency guess
app/export.py      Excel/CSV downloads in Prenew's tracker layout (one row per creator)
app/linking.py     links one person's YouTube/TikTok/Instagram profiles (only when one links to the other)
app/partners.py    imports a collaboration tracker; flags past partners
app/sources/       youtube.py (Data API), tiktok.py (own scraper) + websearch.py
app/store.py       JSON-file database (data/db.json)
static/            the UI (plain HTML/CSS/JS, no build step; settings.js is the Settings dialog)
scripts/dev_fixture.py   SAMPLE data for UI work without keys (data-dev/, never demo it)
```
