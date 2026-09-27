"use strict";

// ---------- Repeating searches ("watches") ----------
// When a search finishes, "Repeat this search" runs it again every day or week by itself. New creators land in the
// list, and in Slack or Teams when a webhook is set in Settings. The search box's recent-searches list shows the
// repeating ones, with Run now and Stop. Uses app.js's helpers ($, api, esc, toast, S, renderJob, startPolling...)
// and its two hooks: scout:job (the job panel was drawn) and scout:recent (the recent searches were drawn).
(function watches() {
  const MAX_MARKETS = 5; // a repeating search spends YouTube quota every run (about 500 units per market)
  let list = null;       // this company's repeating searches, once loaded
  let listFor = "";

  async function load(force = false) {
    if (!S.company) return [];
    if (force || !list || listFor !== S.company.id) {
      try {
        list = await api(`/api/companies/${S.company.id}/watches`);
        listFor = S.company.id;
      } catch { return list || []; }
    }
    return list;
  }

  const sameSet = (a, b) => JSON.stringify([...(a || [])].sort()) === JSON.stringify([...(b || [])].sort());
  const sameSearch = (w, job) => sameSet(w.search.markets, job.markets) && sameSet(w.search.platforms, job.platforms)
    && sameSet(w.search.tags, job.tags) && (w.search.focus || "") === (job.focus || "");

  // The finished search, as a search body: the same markets, platforms, creator types, size and wording.
  const searchOf = (job) => ({
    markets: job.markets, platforms: job.platforms, tags: job.tags || [], focus: job.focus || "",
    size_preset: job.size_preset || "", follower_min: job.follower_min ?? null, follower_max: job.follower_max ?? null,
    deal_types: job.deal_types || [], avoid: job.avoid || [], example_creators: job.example_creators || [],
  });

  function nextRun(w) {
    const hours = Math.round((new Date(w.last_run_at || w.created_at).getTime() + w.every_days * 864e5 - Date.now()) / 36e5);
    if (hours <= 1) return "runs within the hour";
    if (hours < 24) return `next run in ${hours} h`;
    const days = Math.round(hours / 24);
    return `next run in ${days} day${days === 1 ? "" : "s"}`;
  }

  async function chatNote() {
    try {
      const st = await api("/api/settings");
      const chats = [st.slack_webhook_hint && "Slack", st.teams_webhook_hint && "Teams"].filter(Boolean);
      return chats.length ? `New creators will show up in your list and in ${chats.join(" and ")}.`
        : "New creators will show up in your list. Add Slack or Teams in Settings to get a message too.";
    } catch { return "New creators will show up in your list."; }
  }

  const repeatsHtml = (w) => `<span class="muted small" title="Stop it from the search box's recent searches">Repeats ${esc(w.every)}</span>`;

  // Job panel: "Repeat this search" right after a search finished.
  document.addEventListener("scout:job", async (e) => {
    const job = e.detail;
    if (job.status !== "done" || job.mode || job.auto || job.all_markets || (job.markets || []).length > MAX_MARKETS) return;
    const top = $("#job .job-top");
    if (!top || top.querySelector(".watch-add")) return;
    const box = document.createElement("span");
    box.className = "watch-add";
    top.insertBefore(box, top.querySelector('[data-act="dismiss-job"]'));
    const w = (await load(true)).find((x) => sameSearch(x, job)); // fresh: a teammate may have set it up
    if (!box.isConnected) return; // the panel was drawn again meanwhile
    box.innerHTML = w ? repeatsHtml(w)
      : `<button type="button" class="btn small" data-watch="ask" title="Run this search again by itself and get the new creators it finds">Repeat this search</button>`;
  });

  // Recent searches: the repeating ones, with Run now and Stop.
  const listHtml = (ws) => `<div class="recent-head">Repeating searches</div>` + ws.map((w) => `
    <div class="watch-row">
      <span class="watch-what"><span>${esc(w.label)}</span><small>${esc(w.every)} · ${nextRun(w)}</small></span>
      <button type="button" class="btn small" data-watch-run="${esc(w.id)}">Run now</button>
      <button type="button" class="btn small" data-watch-stop="${esc(w.id)}" title="Stop repeating this search">Stop</button>
    </div>`).join("");

  document.addEventListener("scout:recent", async (e) => {
    const el = e.detail;
    const render = (ws) => {
      el.querySelector(".watch-list")?.remove();
      if (!ws.length || el.hidden) return;
      const sec = document.createElement("div");
      sec.className = "watch-list";
      sec.innerHTML = listHtml(ws);
      el.appendChild(sec);
    };
    if (list && listFor === S.company?.id) render(list); // what we know now, then what the server says
    const fresh = await load(true);
    if (el.isConnected && !el.hidden) render(fresh);
  });

  // Clicks in the list shouldn't take the focus from the search box (that would close the list).
  document.addEventListener("mousedown", (e) => { if (e.target.closest(".watch-list")) e.preventDefault(); });

  document.addEventListener("click", async (e) => {
    const ask = e.target.closest("#job [data-watch]");
    const run = e.target.closest("[data-watch-run]");
    const stop = e.target.closest("[data-watch-stop]");
    if (ask) {
      const box = ask.closest(".watch-add");
      if (ask.dataset.watch === "ask") {
        box.innerHTML = `<span class="muted small">Repeat</span>
          <button type="button" class="btn small" data-watch="1">every day</button>
          <button type="button" class="btn small" data-watch="7">every week</button>`;
        box.querySelector("button").focus();
        return;
      }
      if (!S.job || !S.company) return;
      box.querySelectorAll("button").forEach((b) => { b.disabled = true; });
      try {
        const w = await api(`/api/companies/${S.company.id}/watches`, { method: "POST", body: { ...searchOf(S.job), every_days: +ask.dataset.watch } });
        list = [...(await load()).filter((x) => x.id !== w.id), w];
        box.innerHTML = repeatsHtml(w);
        toast(`Scout will repeat this search ${w.every}. ${await chatNote()}`, "ok");
      } catch (err) {
        toast(err.message, "err");
        box.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      }
    } else if (stop) {
      stop.disabled = true;
      try {
        await api(`/api/companies/${S.company.id}/watches/${encodeURIComponent(stop.dataset.watchStop)}`, { method: "DELETE" });
        list = (list || []).filter((w) => w.id !== stop.dataset.watchStop);
        const sec = stop.closest(".watch-list");
        if (list.length) sec.innerHTML = listHtml(list); else sec.remove();
        toast("Stopped repeating that search", "ok");
      } catch (err) { toast(err.message, "err"); stop.disabled = false; }
    } else if (run) {
      run.disabled = true;
      try {
        S.job = await api(`/api/companies/${S.company.id}/watches/${encodeURIComponent(run.dataset.watchRun)}/run`, { method: "POST" });
        S.viewJob = S.job.id;
        S.page = 1;
        S.recent = null;
        hideRecent();
        $("#q").blur();
        loadCreators({ quiet: true });
        renderJob();
        startPolling();
        load(true);
      } catch (err) { toast(err.message, "err"); run.disabled = false; }
    }
  });

  // A few rules of its own: rows with two buttons inside the recent-searches list (whose buttons are full-width rows).
  const style = document.createElement("style");
  style.textContent = `
    .recent .watch-list { border-top: 1px solid var(--line); margin-top: 4px; padding-top: 4px; }
    .recent .watch-row { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 7px; }
    .recent .watch-row:hover { background: var(--surface-2); }
    .recent .watch-what { flex: 1; min-width: 0; display: flex; justify-content: space-between; gap: 12px; }
    .recent .watch-what > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .recent .watch-row .btn { width: auto; flex: none; justify-content: center; border: 1px solid var(--line); background: var(--surface); }
    .recent .watch-row .btn:hover { background: var(--surface-2); }
    .watch-add { display: inline-flex; align-items: center; gap: 6px; }`;
  document.head.appendChild(style);
})();
