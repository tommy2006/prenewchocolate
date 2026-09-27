"use strict";

// ---------- Campaign planner ----------
// "€5,000, goal Sales": the best mix of creators from the list you're looking at (the same filters), with the
// cost range, expected views and cost per 1,000 views. One sponsored post each at their typical views; prices are
// estimates to negotiate from. Uses app.js's helpers ($, api, esc, fmtNum, euro, ICONS, S, queryString...).
(function planner() {
  const GOALS = { sales: "Sales: viewers likely to buy", balanced: "Balanced", awareness: "Awareness: reach in your markets" };
  let last = null; // the latest plan, for the buttons under it

  function button() {
    const head = $(".results-head");
    if (!head || $("#plan-btn")) return;
    const b = document.createElement("button");
    b.type = "button";
    b.id = "plan-btn";
    b.className = "btn small";
    b.title = "Pick the best mix of creators for a budget, from the list below";
    b.innerHTML = `${ICONS.sparkle} Plan a campaign`;
    b.addEventListener("click", open);
    head.insertBefore(b, $("#downloads"));
  }

  function dialog() {
    let dlg = $("#planner");
    if (!dlg) {
      dlg = document.createElement("dialog");
      dlg.id = "planner";
      dlg.className = "dlg dlg-wide planner";
      dlg.setAttribute("aria-labelledby", "planner-title");
      dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
      document.body.appendChild(dlg);
    }
    return dlg;
  }

  function open() {
    if (!S.company) return;
    const p = S.company.profile || {};
    const dlg = dialog();
    dlg.innerHTML = `
      <form id="plan-form" autocomplete="off">
        <div class="dlg-head">
          <div><h2 id="planner-title">Plan a campaign</h2>
            <p>The best mix for your budget from the creators the list shows now. Change the filters to plan for other markets or sizes.</p></div>
          <button type="button" class="x" data-act="close" aria-label="Close">${ICONS.x}</button>
        </div>
        <div class="dlg-body">
          <div class="plan-form">
            <label class="field"><span>Budget (€)</span>
              <input type="number" id="plan-budget" min="50" step="50" value="${esc(String(Math.max(500, (p.budget_max || 0) * 8 || 5000)))}" required></label>
            <label class="field"><span>Goal</span>
              <select id="plan-goal">${Object.entries(GOALS).map(([k, label]) => `<option value="${k}" ${k === (p.goal || "balanced") ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></label>
            <label class="field"><span>Up to</span>
              <select id="plan-max">${[5, 8, 10, 12, 15, 20].map((n) => `<option value="${n}" ${n === 10 ? "selected" : ""}>${n} creators</option>`).join("")}</select></label>
            <div class="plan-checks">
              <label class="check"><input type="checkbox" id="plan-email"> Only creators with an email</label>
              <label class="check"><input type="checkbox" id="plan-new"> Only creators you haven't worked with</label>
              <button type="submit" class="btn primary" id="plan-go">${ICONS.sparkle} Plan it</button>
            </div>
          </div>
          <div id="plan-out" aria-live="polite"></div>
        </div>
      </form>`;
    $("#plan-form").addEventListener("submit", (e) => { e.preventDefault(); run(); });
    dlg.showModal();
    run();
  }

  async function run() {
    const out = $("#plan-out");
    const go = $("#plan-go");
    go.disabled = true;
    out.innerHTML = `<div class="loading-line"><span class="spinner"></span> Picking the best mix…</div>`;
    const body = {
      budget: +$("#plan-budget").value || 5000,
      goal: $("#plan-goal").value,
      max_creators: +$("#plan-max").value,
      need_email: $("#plan-email").checked,
      new_only: $("#plan-new").checked,
    };
    try {
      last = await api(`/api/companies/${S.company.id}/plan?${queryString({ page: "", page_size: "" })}`, { method: "POST", body });
      out.innerHTML = render(last);
    } catch (err) {
      out.innerHTML = `<p class="err-line">${esc(err.message)}</p>`;
    } finally { go.disabled = false; }
  }

  const mix = (obj) => Object.entries(obj || {}).map(([k, n]) => `${esc(k)} ${n}`).join(" · ");

  function render(r) {
    if (!r.count) {
      const why = Object.entries(r.left_out || {}).map(([k, n]) => `${n} with ${esc(k)}`).join(", ");
      return `<div class="empty small"><h3>Nothing fits yet</h3><p>No creator in the list fits this budget and these choices${why ? ` (left out: ${why})` : ""}. Raise the budget, allow more creators, or widen the filters.</p></div>`;
    }
    const vs = r.single_best && r.views > r.single_best.views
      ? `<p class="plan-vs">For the same budget, the single biggest creator you could book is <b>${esc(r.single_best.name)}</b>: about ${fmtNum(r.single_best.views)} views. This mix reaches about <b>${fmtNum(r.views)}</b> (${(r.views / r.single_best.views).toFixed(1)}×) across ${Object.keys(r.markets).length} market${Object.keys(r.markets).length === 1 ? "" : "s"}.</p>` : "";
    const left = Object.entries(r.left_out || {}).map(([k, n]) => `${n} ${esc(k)}`).join(" · ");
    return `
      <div class="plan-tiles">
        <div><b>${r.count}</b><span>creators · ${r.with_email} with email${r.hidden_gems ? ` · ${r.hidden_gems} hidden gem${r.hidden_gems === 1 ? "" : "s"}` : ""}</span></div>
        <div><b>€${fmtNum(r.cost.low)}–${fmtNum(r.cost.high)}</b><span>estimated cost (budget €${fmtNum(r.budget)})</span></div>
        <div><b>${fmtNum(r.views)}</b><span>expected views, one post each</span></div>
        <div><b>€${r.cost_per_1k_views ?? "—"}</b><span>per 1,000 views</span></div>
      </div>
      ${vs}
      <p class="plan-mix">${mix(r.markets)} · ${mix(r.platforms)} · ${mix(r.sizes)} followers</p>
      <div class="table-wrap"><table class="plan-table">
        <thead><tr><th>Creator</th><th>Market</th><th class="num c-hide-sm">Followers</th><th class="num">Typical views</th><th class="num">Est. price</th><th class="num">Fit</th></tr></thead>
        <tbody>${r.items.map((i) => `
          <tr data-plan-open="${esc(i.id)}" title="Open ${esc(i.name)}">
            <td><span class="plat plat-${i.platform}">${ICONS[i.platform] || ""}</span> <b>${esc(i.name)}</b>
              ${i.partner ? '<span class="tag partner">🤝 Past partner</span>' : ""}${i.hidden_gem ? '<span class="tag gem">💎 Gem</span>' : ""}
              ${i.email ? "" : '<span class="muted small">· no email</span>'}</td>
            <td>${esc(i.market || "—")}</td>
            <td class="num c-hide-sm">${fmtNum(i.followers)}</td>
            <td class="num">${fmtNum(i.views)}</td>
            <td class="num">${euro(i.price)}</td>
            <td class="num">${i.fit ?? "—"}</td>
          </tr>`).join("")}</tbody></table></div>
      <p class="plan-note">${esc(r.note)}${left ? ` Left out: ${left}.` : ""}</p>
      <div class="plan-actions">
        <button type="button" class="btn primary" data-plan-act="shortlist">${ICONS.star} Add all to shortlist</button>
        ${S.meta.sources.ai ? `<button type="button" class="btn" data-plan-act="pitches">${ICONS.mail} Draft their messages</button>` : ""}
        <a class="btn" href="/api/companies/${esc(S.company.id)}/export?ids=${encodeURIComponent(r.items.map((i) => i.id).join(","))}&status=any&format=xlsx" download>${ICONS.download} Download Excel</a>
      </div>`;
  }

  document.addEventListener("click", async (e) => {
    const row = e.target.closest("[data-plan-open]");
    if (row) { $("#planner").close(); openDetail(row.dataset.planOpen); return; }
    const act = e.target.closest("[data-plan-act]");
    if (!act || !last) return;
    const ids = last.items.map((i) => i.id);
    if (act.dataset.planAct === "shortlist") {
      act.disabled = true;
      try {
        await api(`/api/companies/${S.company.id}/creators/bulk-status`, { method: "POST", body: { ids, status: "shortlisted" } });
        toast(`${ids.length} creators added to the shortlist`, "ok");
        updateShortlistCount();
        loadCreators({ quiet: true });
      } catch (err) { toast(err.message, "err"); act.disabled = false; }
    } else if (act.dataset.planAct === "pitches") {
      $("#planner").close();
      startTask("pitches", { ids });
    }
  });

  // app.js renders the page after loading; add the button once the results header exists.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", button);
  else button();
})();
