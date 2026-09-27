"use strict";

// ---------- Market map, and adding a creator from a link ----------
// Market map: per market, what Scout has found (sizes, gems, past partners, emails, typical views and price, games,
// best matches); click a market to filter the list to it.
// Add a creator: paste a YouTube, TikTok or Twitch link (in this window or the search box), or use the
// "Scout this creator" bookmarklet on any creator's page. Uses app.js's helpers ($, api, esc, fmtNum, ICONS, S...).
(function tools() {
  const SIZE_LABELS = { nano: "under 10k", micro: "10k–50k", mid: "50k–250k", macro: "250k+" };
  const LINK = /^(https?:\/\/)?((www|m)\.)?(youtube\.com|youtu\.be|tiktok\.com|twitch\.tv)\/\S+$/i;

  function addButtons() {
    const head = $(".results-head");
    if (!head || $("#map-btn")) return;
    const anchor = $("#plan-btn") || $("#downloads");
    for (const [id, label, title, fn] of [
      ["map-btn", "Market map", "What Scout has found in each market", openMap],
      ["add-btn", "Add a creator", "Score any creator from a YouTube, TikTok or Twitch link", () => openAdd("")],
    ]) {
      const b = document.createElement("button");
      b.type = "button";
      b.id = id;
      b.className = "btn small";
      b.title = title;
      b.textContent = label;
      b.addEventListener("click", fn);
      head.insertBefore(b, anchor);
    }
  }

  function dialog(id, cls = "dlg dlg-wide tools") {
    let dlg = document.getElementById(id);
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = id;
      dlg.className = cls;
      dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
      document.body.appendChild(dlg);
    }
    return dlg;
  }

  // ---- Market map ----
  async function openMap() {
    if (!S.company) return;
    const dlg = dialog("market-map");
    dlg.innerHTML = `<div class="dlg-head"><div><h2>Market map</h2><p>What Scout has found in each market so far. Click a market to see its creators.</p></div>
      <button type="button" class="x" data-act="close" aria-label="Close">${ICONS.x}</button></div>
      <div class="dlg-body"><div class="loading-line"><span class="spinner"></span> Counting…</div></div>`;
    dlg.showModal();
    let rows;
    try { rows = await api(`/api/companies/${S.company.id}/market-map`); }
    catch (err) { $(".dlg-body", dlg).innerHTML = `<p class="err-line">${esc(err.message)}</p>`; return; }
    const most = Math.max(1, ...rows.map((r) => r.creators));
    $(".dlg-body", dlg).innerHTML = rows.length ? `<div class="table-wrap"><table class="map-table">
      <thead><tr><th>Market</th><th class="num">Creators</th><th>Sizes</th><th class="num">Gems</th><th class="num" title="Past partners from your tracker">Partners</th>
        <th class="num">Email</th><th class="num">Typical views</th><th class="num">Typical price</th><th>Top games</th><th>Best matches</th></tr></thead>
      <tbody>${rows.map((r) => `
        <tr ${r.market ? `data-map-market="${esc(r.market)}" title="Show the creators in ${esc(r.name)}"` : ""}>
          <td><b>${esc(r.name)}</b></td>
          <td class="num">${r.creators}<span class="map-bar"><i style="width:${Math.round((100 * r.creators) / most)}%"></i></span></td>
          <td><span class="map-sizes">${Object.entries(r.sizes).filter(([, n]) => n).map(([k, n]) => `<span title="${n} with ${esc(SIZE_LABELS[k])} followers">${esc(SIZE_LABELS[k])} ${n}</span>`).join("")}</span></td>
          <td class="num">${r.hidden_gems || "—"}</td>
          <td class="num">${r.past_partners || "—"}</td>
          <td class="num">${r.with_email}/${r.creators}</td>
          <td class="num">${fmtNum(r.median_views)}</td>
          <td class="num">${r.median_price ? `€${fmtNum(r.median_price)}` : "—"}</td>
          <td>${esc(r.games.join(", ") || "—")}</td>
          <td>${r.best.map((b) => `<a href="#" data-map-open="${esc(b.id)}">${esc(b.name)}</a>`).join(", ")}</td>
        </tr>`).join("")}</tbody></table></div>
      <p class="plan-note">Creators with 1,000+ followers in your list, not counting ones marked not a fit. Typical price: the middle of their estimated price per post.</p>`
      : `<p class="muted">No creators yet. Run a search first.</p>`;
  }

  // ---- Add a creator from a link ----
  function bookmarklet() {
    const code = `javascript:void(window.open('${location.origin}/?add='+encodeURIComponent(location.href)))`;
    return `<a class="btn small bookmarklet" href="${esc(code)}" title="Drag me to your bookmarks bar" onclick="event.preventDefault()">${ICONS.sparkle} Scout this creator</a>`;
  }

  function openAdd(link) {
    if (!S.company) return;
    const dlg = dialog("add-creator", "dlg tools");
    dlg.innerHTML = `<form id="add-form" autocomplete="off">
      <div class="dlg-head"><div><h2>Add a creator</h2><p>Paste a link to a YouTube, TikTok or Twitch profile, or to one of their videos. Scout looks them up, finds their contacts and scores them for ${esc(S.company.name)}.</p></div>
        <button type="button" class="x" data-act="close" aria-label="Close">${ICONS.x}</button></div>
      <div class="dlg-body">
        <div class="add-row"><input type="url" id="add-url" required placeholder="https://www.youtube.com/@creator" value="${esc(link)}" aria-label="Link to a creator">
          <button type="submit" class="btn primary" id="add-go">Add and score</button></div>
        <div id="add-out" aria-live="polite"></div>
        <div class="add-tip"><b>On any creator's page:</b> drag ${bookmarklet()} to your bookmarks bar. Clicking it on a YouTube, TikTok or Twitch page sends that creator here.</div>
      </div></form>`;
    $("#add-form").addEventListener("submit", (e) => { e.preventDefault(); add($("#add-url").value); });
    dlg.showModal();
    if (link) add(link); else $("#add-url").focus();
  }

  async function add(url) {
    const out = $("#add-out");
    const go = $("#add-go");
    go.disabled = true;
    out.innerHTML = `<div class="loading-line"><span class="spinner"></span> Looking them up…</div>`;
    let job;
    try {
      job = await api(`/api/companies/${S.company.id}/add-creator`, { method: "POST", body: { url } });
      for (let i = 0; i < 240 && (job.status === "queued" || job.status === "running"); i++) {
        await new Promise((r) => setTimeout(r, 1500));
        job = await api(`/api/jobs/${job.id}`);
        const now = (job.steps || []).filter((s) => s.status === "running").map((s) => s.label).join(" · ");
        if (now) out.innerHTML = `<div class="loading-line"><span class="spinner"></span> ${esc(now)}…</div>`;
      }
    } catch (err) {
      out.innerHTML = `<p class="err-line">${esc(err.message)}</p>`;
      go.disabled = false;
      return;
    }
    go.disabled = false;
    if (job.status !== "done" || !job.creator_id) {
      out.innerHTML = `<p class="err-line">${esc(job.error || "That didn't work. Check the link and try again.")}</p>`;
      return;
    }
    $("#add-creator").close();
    toast(job.new ? "Added and scored" : "Already in your list", "ok");
    loadCreators({ quiet: true });
    openDetail(job.creator_id);
  }

  // ---- Wiring ----
  document.addEventListener("click", (e) => {
    const market = e.target.closest("[data-map-market]");
    const open = e.target.closest("[data-map-open]");
    if (open) {
      e.preventDefault();
      $("#market-map").close();
      openDetail(open.dataset.mapOpen);
    } else if (market) {
      $("#market-map").close();
      S.f.markets = [market.dataset.mapMarket];
      renderFilters();
      searchChanged();
    }
  });

  // A creator link pasted in the search box: add that creator instead of reading it as a search.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.target.id !== "q" || !LINK.test(e.target.value.trim())) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const link = e.target.value.trim();
    e.target.value = "";
    openAdd(link);
  }, true);

  // Sent by the bookmarklet: /?add=<link>. Wait until the app has loaded the company, then add.
  const sent = new URLSearchParams(location.search).get("add");
  if (sent) {
    history.replaceState(null, "", location.pathname);
    let tries = 0;
    const wait = setInterval(() => {
      if (S.company || ++tries > 50) { clearInterval(wait); if (S.company) openAdd(sent); }
    }, 200);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addButtons);
  else addButtons();
})();
