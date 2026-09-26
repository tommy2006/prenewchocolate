"use strict";

// ---------- Helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, { method = "GET", body } = {}) {
  const r = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* not JSON */ }
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.json();
}

function fmtNum(n) {
  if (n == null) return "—";
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1e4) return Math.round(n / 1e3) + "k";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "k";
  return String(Math.round(n));
}
const pct = (r) => (r == null ? "—" : (r * 100).toFixed(r < 0.1 ? 1 : 0) + "%");
const scoreClass = (s) => (s >= 80 ? "s-hi" : s >= 60 ? "s-mid" : "s-lo");
const initials = (name) => (name || "?").replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
function hue(str) { let h = 0; for (const ch of str || "") h = (h * 31 + ch.charCodeAt(0)) % 360; return h; }
const placeholder = (name) => `<div class="initials" style="background:hsl(${hue(name)} 55% 45%)">${esc(initials(name))}</div>`;
const daysAgo = (d) => (d == null ? "—" : d === 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`);

const ICONS = {
  youtube: '<svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M23 7.2a3 3 0 0 0-2.1-2.1C19 4.6 12 4.6 12 4.6s-7 0-8.9.5A3 3 0 0 0 1 7.2 31 31 0 0 0 .5 12a31 31 0 0 0 .5 4.8 3 3 0 0 0 2.1 2.1c1.9.5 8.9.5 8.9.5s7 0 8.9-.5a3 3 0 0 0 2.1-2.1 31 31 0 0 0 .5-4.8 31 31 0 0 0-.5-4.8zM9.7 15.1V8.9l5.8 3.1-5.8 3.1z"/></svg>',
  tiktok: '<svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M16.6 5.8A4.3 4.3 0 0 1 15.5 3h-3.1v12.4a2.6 2.6 0 1 1-2.6-2.6c.3 0 .5 0 .8.1V9.7a5.8 5.8 0 1 0 5 5.7V9.1a7.4 7.4 0 0 0 4.3 1.4V7.4a4.3 4.3 0 0 1-3.3-1.6z"/></svg>',
  instagram: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>',
  x: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  ext: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  star: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z"/></svg>',
  starOn: '<svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3l-5.6 2.9 1.1-6.2L3 9.6l6.2-.9z"/></svg>',
  copy: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/></svg>',
  mail: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>',
  sparkle: '<svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.9 5.6 5.6 1.9-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9zM19 15l.9 2.1 2.1.9-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z"/></svg>',
  eyeOff: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6 0 9.5 7 9.5 7a17 17 0 0 1-3 3.8M6.3 6.3C3.8 8 2.5 12 2.5 12s3.5 7 9.5 7a9.6 9.6 0 0 0 4.3-1"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>',
};

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "err" ? 6000 : 3500);
}

// ---------- State ----------
// Search criteria (saved per company, used for both filtering and new searches)
const DEFAULT_SEARCH = { tags: [], markets: [], platforms: [], tiers: [], follower_min: null, follower_max: null, deal_types: [], avoid: [], example_creators: [], ai_scout: false };
// ...plus filters that only narrow what's already in the library
const DEFAULT_FILTERS = { ...DEFAULT_SEARCH, q: "", language: "", min_score: 0, min_eng: 0, has_email: false, gems: false, show_hidden: false, sort: "match" };
const S = {
  meta: null,
  companies: [],
  company: null,
  view: "discover",
  f: { ...DEFAULT_FILTERS },
  page: 1,
  job: null,
  pollTimer: null,
  polls: 0,
  detailId: null,
  pitch: null,
  viewJob: null, // when set, the grid shows exactly what that search found
};

// ---------- Reusable chip controls ----------
function chipSelect(root, options, selected, onChange) {
  const sel = new Set(selected);
  root.innerHTML = options.map((o) => `
    <button type="button" class="chip ${sel.has(o.value) ? "on" : ""}" data-v="${esc(o.value)}"
      ${o.disabled ? "disabled" : ""} title="${esc(o.title || "")}">${o.icon || ""}${esc(o.label)}</button>`).join("");
  root.onclick = (e) => {
    const b = e.target.closest("button[data-v]");
    if (!b || b.disabled) return;
    const v = b.dataset.v;
    sel.has(v) ? sel.delete(v) : sel.add(v);
    b.classList.toggle("on", sel.has(v));
    onChange?.(options.map((o) => o.value).filter((x) => sel.has(x)));
  };
  return { get: () => options.map((o) => o.value).filter((x) => sel.has(x)) };
}

function chipInput(root, initial = [], placeholderText = "Type and press Enter", onChange = null) {
  let values = [...initial];
  const changed = () => onChange?.([...values]);
  const render = () => {
    root.innerHTML = values.map((v, i) => `<span class="tchip">${esc(v)}<button type="button" data-i="${i}" aria-label="Remove ${esc(v)}">×</button></span>`).join("")
      + `<input type="text" placeholder="${esc(placeholderText)}">`;
    const input = $("input", root);
    input.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === ",") && input.value.trim()) { e.preventDefault(); add(input.value); }
      else if (e.key === "Enter") e.preventDefault();
      else if (e.key === "Backspace" && !input.value && values.length) { values.pop(); render(); changed(); $("input", root).focus(); }
    });
    input.addEventListener("blur", () => { if (input.value.trim()) add(input.value, false); });
  };
  const add = (v, refocus = true) => {
    v = v.trim().replace(/,$/, "");
    if (v && !values.some((x) => x.toLowerCase() === v.toLowerCase())) { values.push(v); changed(); }
    render();
    if (refocus) $("input", root).focus();
  };
  root.onclick = (e) => {
    const b = e.target.closest("button[data-i]");
    if (b) { values.splice(+b.dataset.i, 1); render(); changed(); }
    else if (e.target === root) $("input", root).focus();
  };
  render();
  return { get: () => { const pending = $("input", root).value.trim(); if (pending) add(pending, false); return values; }, add };
}

// ---------- Company ----------
function setCompany(company) {
  S.company = company;
  try { localStorage.setItem("scout.company", company.id); } catch { /* storage blocked */ }
  $("#company-name").textContent = company.name;
  $("#company-dot").textContent = initials(company.name).slice(0, 1);
  $("#company-dot").style.background = `hsl(${hue(company.name)} 60% 42%)`;
  $("#company-dot").style.color = "#fff";
  $("#export-csv").href = `/api/companies/${company.id}/export?status=shortlist&format=xlsx`;
  S.f = { ...DEFAULT_FILTERS, ...(company.search || {}) };
  // Older saved searches used size chips; turn them into a slider range once.
  if (S.f.tiers?.length && S.f.follower_min == null && S.f.follower_max == null) {
    const picked = S.meta.tiers.filter((t) => S.f.tiers.includes(t.key));
    S.f.follower_min = Math.min(...picked.map((t) => t.min)) || null;
    S.f.follower_max = picked.some((t) => t.max == null) ? null : Math.max(...picked.map((t) => t.max));
  }
  S.f.tiers = [];
  S.viewJob = null;
  S.page = 1;
  $("#q").value = "";
  renderFilters();
  refresh();
  stopPolling();
  $("#job").hidden = true;
  resumeJob();
}

function renderCompanyMenu() {
  const menu = $("#company-list");
  menu.innerHTML = S.companies.map((c) => `
      <button data-company="${esc(c.id)}"><span class="company-dot" style="background:hsl(${hue(c.name)} 60% 42%);color:#fff">${esc(initials(c.name).slice(0, 1))}</span>
      ${esc(c.name)}${c.id === S.company?.id ? '<span class="check-mark">✓</span>' : ""}</button>`).join("")
    + `<div class="sep"></div>
       <button data-act="edit-company">Edit ${esc(S.company?.name || "")}</button>
       <button data-act="new-company">+ Add a company</button>`;
}

function toggleCompanyMenu(open) {
  const menu = $("#company-list");
  open = open ?? menu.hidden;
  if (open) renderCompanyMenu();
  menu.hidden = !open;
  $("#company-btn").setAttribute("aria-expanded", String(open));
}

// ---------- Search area ----------
// Creator type, market, platform and size both filter the library and drive "Find new creators".
function renderFilters() {
  const sources = S.meta.sources;
  renderTagPicker();
  renderMarketPicker();
  chipSelect($("#f-platforms"), Object.entries(S.meta.platforms).map(([k, label]) => ({ value: k, label, icon: ICONS[k] })),
    S.f.platforms, (v) => { S.f.platforms = v; searchChanged(); });
  renderSize();
  renderSuggestions();

  // "More options": settings for new searches
  chipSelect($("#c-deals"), S.meta.deal_types.map((d) => ({ value: d, label: d })), S.f.deal_types,
    (v) => { S.f.deal_types = v; searchChanged({ reload: false }); });
  chipInput($("#c-avoid"), S.f.avoid, "e.g. Gambling, a competitor…", (v) => { S.f.avoid = v; searchChanged({ reload: false }); });
  chipInput($("#c-examples"), S.f.example_creators, "@handle or profile link", (v) => { S.f.example_creators = v; searchChanged({ reload: false }); });
  $("#c-scout").checked = S.f.ai_scout;

  // "More options": filters on results
  $("#f-language").innerHTML = '<option value="">Any language</option>'
    + Object.entries(S.meta.languages).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#f-language").value = S.f.language;
  $("#f-sort").value = S.f.sort;
  $("#f-min-score").value = S.f.min_score;
  $("#min-score-val").textContent = S.f.min_score;
  $("#f-min-eng").value = String(S.f.min_eng);
  $("#f-has-email").checked = S.f.has_email;
  $("#f-gems").checked = S.f.gems;
  $("#f-hidden").checked = S.f.show_hidden;
  updateAdvCount();

  const missing = [];
  if (!sources.ai) missing.push("an AI key");
  if (!sources.youtube) missing.push("a YouTube key");
  if (!sources.tiktok) missing.push("an Apify token (TikTok + Instagram)");
  $("#setup-warning").hidden = !missing.length;
  $("#setup-warning").innerHTML = `<span>Finish setup: add ${missing.join(", ")}.</span> <button class="btn small dark" data-act="settings">Open settings</button>`;
  const scoutOk = S.meta.ai.web_search;
  $("#c-scout").disabled = !scoutOk;
  $("#c-scout-note").textContent = scoutOk ? "" : ` Needs Claude as the AI (now: ${S.meta.ai.label}).`;
}

// ---------- Size slider ----------
// Slider stops (followers). Index 0 = no minimum, last = no maximum.
const SIZE_STEPS = [0, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 250000, 500000, 1000000, 5000000, null];
const SIZE_PRESETS = [
  { label: "Any size", min: null, max: null },
  { label: "Nano · under 10k", min: 1000, max: 10000 },
  { label: "Micro · 10k–50k", min: 10000, max: 50000 },
  { label: "Mid · 50k–250k", min: 50000, max: 250000 },
  { label: "Macro · 250k+", min: 250000, max: null },
];

function sizeIndex(value, isMax) {
  if (value == null || (!isMax && value === 0)) return isMax ? SIZE_STEPS.length - 1 : 0;
  // nearest stop, so saved values that aren't exact stops still land sensibly
  let best = isMax ? SIZE_STEPS.length - 2 : 1;
  SIZE_STEPS.forEach((s, i) => {
    if (s != null && Math.abs(s - value) < Math.abs((SIZE_STEPS[best] ?? Infinity) - value)) best = i;
  });
  return best;
}

function sizeText(min, max) {
  if (!min && max == null) return "Any size";
  if (max == null) return `${fmtNum(min)}+ followers`;
  if (!min) return `Up to ${fmtNum(max)} followers`;
  return `${fmtNum(min)} – ${fmtNum(max)} followers`;
}

function renderSize() {
  const lo = sizeIndex(S.f.follower_min, false);
  const hi = sizeIndex(S.f.follower_max, true);
  $("#size-lo").value = lo;
  $("#size-hi").value = hi;
  const last = SIZE_STEPS.length - 1;
  $("#range-fill").style.left = `${(lo / last) * 100}%`;
  $("#range-fill").style.width = `${((hi - lo) / last) * 100}%`;
  $("#size-label").textContent = sizeText(S.f.follower_min, S.f.follower_max);
  $("#f-sizes").innerHTML = SIZE_PRESETS.map((p, i) => {
    const on = (p.min || 0) === (S.f.follower_min || 0) && (p.max ?? null) === (S.f.follower_max ?? null);
    return `<button type="button" class="chip small-chip ${on ? "on" : ""}" data-size="${i}">${esc(p.label)}</button>`;
  }).join("");
}

let sizeTimer;
function sizeFromSlider(which) {
  let lo = +$("#size-lo").value;
  let hi = +$("#size-hi").value;
  if (lo >= hi) {  // keep the handles apart
    if (which === "lo") lo = Math.max(0, hi - 1);
    else hi = Math.min(SIZE_STEPS.length - 1, lo + 1);
  }
  S.f.follower_min = SIZE_STEPS[lo] || null;
  S.f.follower_max = SIZE_STEPS[hi];
  renderSize();
  clearTimeout(sizeTimer);
  sizeTimer = setTimeout(() => searchChanged(), 250);
}

function setSize(min, max) {
  S.f.follower_min = min;
  S.f.follower_max = max;
  renderSize();
  searchChanged();
}

// ---------- Suggested searches ----------
function sizeShort(min, max) {
  return !min && max == null ? "any size" : max == null ? `${fmtNum(min)}+` : `${fmtNum(min || 0)}–${fmtNum(max)}`;
}

function renderSuggestions() {
  let hidden = false;
  try { hidden = localStorage.getItem("scout.hideSuggestions") === "1"; } catch { /* storage blocked */ }
  const list = S.company.suggested_searches || [];
  $("#suggest-strip").hidden = hidden;
  $("#show-suggest").hidden = !hidden;
  $("#suggest-cards").innerHTML = list.map((s, i) => `
      <button type="button" class="sugg-card" data-sugg="${i}" title="Fill in this search">
        <b>${esc(s.title)}</b>
        <span>${esc(s.description)}</span>
        <small>${esc(s.markets.map((m) => S.meta.markets[m]?.name || m).join(", "))} · ${esc(s.platforms.map((p) => S.meta.platforms[p]).join(", "))} · ${esc(sizeShort(s.follower_min, s.follower_max))}</small>
      </button>`).join("")
    + (S.meta.sources.ai ? `<button type="button" class="sugg-card more" data-act="more-suggestions">${ICONS.sparkle}<b>More ideas</b><span>Let the AI suggest searches for ${esc(S.company.name)}</span></button>` : "")
    + (!list.length && !S.meta.sources.ai ? `<span class="hint">Set up an AI in Settings to get suggested searches.</span>` : "");
}

function applySuggestion(s) {
  S.f.q = s.query || "";
  $("#q").value = S.f.q;
  S.f.tags = [...s.tags];
  S.f.markets = [...s.markets];
  S.f.platforms = s.platforms.length === Object.keys(S.meta.platforms).length ? [] : [...s.platforms];
  S.f.follower_min = s.follower_min || null;
  S.f.follower_max = s.follower_max ?? null;
  renderFilters();
  searchChanged();
  const btn = $("#find-btn");
  btn.classList.remove("pulse");
  void btn.offsetWidth;
  btn.classList.add("pulse");
  toast(`“${s.title}” filled in. Press Find new creators to search the platforms.`);
}

async function moreSuggestions(button) {
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span><b>Thinking…</b><span>Writing new search ideas</span>`;
  try {
    const r = await api(`/api/companies/${S.company.id}/suggest-searches`, { method: "POST" });
    S.company.suggested_searches = r.suggested_searches;
    renderSuggestions();
    $("#suggest-cards").scrollTo({ left: 0, behavior: "smooth" });
    toast(r.added ? `${r.added} new search ideas` : "No new ideas this time");
  } catch (err) {
    toast(err.message, "err");
    renderSuggestions();
  }
}

function renderTagPicker() {
  const chosen = S.f.tags;
  const lower = chosen.map((t) => t.toLowerCase());
  const ideas = (S.company.suggested_tags || []).filter((t) => !lower.includes(t.toLowerCase()));
  $("#c-tags").innerHTML =
    chosen.map((t, i) => `<button type="button" class="chip on" data-tag-remove="${i}" aria-label="Remove ${esc(t)}">${esc(t)}<span class="x-mark">×</span></button>`).join("")
    + ideas.map((t) => `<button type="button" class="chip sugg" data-tag-add="${esc(t)}">+ ${esc(t)}</button>`).join("")
    + `<input class="chip-text" id="tag-input" placeholder="Type your own…" aria-label="Add a creator type">`
    + `<button type="button" class="chip ghost" data-act="suggest-tags" title="Ask the AI for more creator types that fit ${esc(S.company.name)}">${ICONS.sparkle} ${ideas.length ? "More ideas" : "Suggest types"}</button>`;
  $("#tag-input").addEventListener("keydown", (e) => {
    const v = e.target.value.trim().replace(/,$/, "");
    if ((e.key === "Enter" || e.key === ",") && v) {
      e.preventDefault();
      addTag(v);
      $("#tag-input").focus();
    }
  });
}

function addTag(tag) {
  if (!S.f.tags.some((t) => t.toLowerCase() === tag.toLowerCase())) S.f.tags = [...S.f.tags, tag];
  renderTagPicker();
  searchChanged();
}

function renderMarketPicker() {
  const chosen = S.f.markets;
  const rest = Object.entries(S.meta.markets).filter(([k]) => !chosen.includes(k));
  $("#c-markets").innerHTML =
    chosen.map((m) => `<button type="button" class="chip on" data-market-remove="${m}" aria-label="Remove ${esc(S.meta.markets[m]?.name || m)}">${esc(S.meta.markets[m]?.name || m)}<span class="x-mark">×</span></button>`).join("")
    + `<select class="chip-select" id="market-add" aria-label="Add a market"><option value="">+ Add market</option>`
    + rest.map(([k, m]) => `<option value="${k}">${esc(m.name)}</option>`).join("") + `</select>`
    + (chosen.length ? "" : `<span class="hint">Showing all markets. Pick at least one to find new creators.</span>`);
  $("#market-add").addEventListener("change", (e) => {
    if (!e.target.value) return;
    S.f.markets = [...S.f.markets, e.target.value];
    renderMarketPicker();
    searchChanged();
  });
}

function updateAdvCount() {
  const n = S.f.deal_types.length + S.f.avoid.length + S.f.example_creators.length + (S.f.ai_scout ? 1 : 0)
    + (S.f.language ? 1 : 0) + (S.f.min_score ? 1 : 0) + (S.f.min_eng ? 1 : 0)
    + (S.f.has_email ? 1 : 0) + (S.f.gems ? 1 : 0) + (S.f.show_hidden ? 1 : 0);
  $("#adv-count").hidden = !n;
  $("#adv-count").textContent = n;
}

let saveTimer;
// Search criteria changed: remember them for this company, and refresh the grid.
function searchChanged({ reload = true } = {}) {
  clearTimeout(saveTimer);
  const body = Object.fromEntries(Object.keys(DEFAULT_SEARCH).map((k) => [k, S.f[k]]));
  S.company.search = body;
  saveTimer = setTimeout(() => api(`/api/companies/${S.company.id}/search`, { method: "PUT", body }).catch(() => {}), 400);
  if (reload) filtersChanged();
  else updateAdvCount();
}

let searchTimer;
function filtersChanged({ debounce = false } = {}) {
  S.page = 1;
  S.viewJob = null; // touching the filters means browsing the whole library again
  updateAdvCount();
  clearTimeout(searchTimer);
  if (debounce) searchTimer = setTimeout(loadCreators, 220);
  else loadCreators();
}

function queryString(extra = {}) {
  const f = S.f;
  const p = new URLSearchParams({
    q: f.q, tags: f.tags.join(","), platforms: f.platforms.join(","), tiers: f.tiers.join(","), markets: f.markets.join(","),
    fmin: f.follower_min || 0, fmax: f.follower_max || 0,
    language: f.language, min_score: f.min_score, min_eng: f.min_eng, has_email: f.has_email, gems: f.gems,
    status: f.show_hidden ? "hidden" : "", sort: f.sort, page: S.page, page_size: 30, job: S.viewJob || "", ...extra,
  });
  return p.toString();
}

// ---------- Grid ----------
async function loadCreators({ quiet = false } = {}) {
  if (!S.company) return;
  let data;
  try {
    data = await api(`/api/companies/${S.company.id}/creators?${queryString()}`);
  } catch (e) {
    if (!quiet) toast(e.message, "err");
    return;
  }
  S.page = data.page;
  renderGrid(data);
}

function cardHtml(c) {
  const img = c.cover ? `<img src="${esc(c.cover)}" alt="" loading="lazy" data-name="${esc(c.name)}">` : placeholder(c.name);
  const place = [fmtNum(c.followers), c.country, c.niche || S.meta.tiers.find((t) => t.key === c.tier)?.label].filter(Boolean).join(" · ");
  const starred = c.status && c.status !== "hidden";
  return `
  <article class="card" data-id="${esc(c.id)}" tabindex="0" aria-label="${esc(c.name)}, match ${c.score}">
    <div class="cover">
      ${img}
      <span class="plat plat-${c.platform}" title="${esc(S.meta.platforms[c.platform])}">${ICONS[c.platform]}</span>
      <span class="score ${scoreClass(c.score)}" title="Match score">${c.score}</span>
      ${c.is_new ? '<span class="ribbon">NEW</span>' : ""}
      <span class="badges">
        ${c.hidden_gem ? '<span class="badge" title="Hidden gem: small, highly engaged and on-niche">💎</span>' : ""}
        ${starred ? `<span class="badge star" title="On your shortlist">${ICONS.starOn}</span>` : ""}
      </span>
      <div class="hover">
        <p>${esc(c.summary)}</p>
        ${c.games?.length ? `<p class="games">🎮 ${esc(c.games.join(", "))}</p>` : ""}
        ${c.avg_views != null ? `<p class="games">${fmtNum(c.avg_views)} avg views${c.views_window ? ` · ${esc(c.views_window)}` : ""}${c.trend ? ` · ${esc(c.trend.toLowerCase())}` : ""}</p>` : ""}
        <div class="tags">${c.tags.map((t) => `<span>${esc(t)}</span>`).join("")}</div>
        <span class="more">Click for details →</span>
      </div>
    </div>
    <div class="meta">
      <h3>${esc(c.name)}</h3>
      <p>${esc(place)}</p>
    </div>
  </article>`;
}

function renderGrid(data) {
  const grid = $("#grid");
  const filtered = S.f.q || S.f.tags.length || S.f.platforms.length || S.f.tiers.length || S.f.markets.length || S.f.language
    || S.f.min_score || S.f.min_eng || S.f.has_email || S.f.gems || S.f.show_hidden;
  if (!data.library_size) {
    $("#results-count").innerHTML = "";
    grid.innerHTML = `
      <div class="empty">
        <h2>No creators yet for ${esc(S.company.name)}</h2>
        <p>Pick the creator types and markets you want above, then press <b>Find new creators</b>. Scout searches YouTube, TikTok and Instagram in each market's own language and ranks small, genuinely engaged creators first.</p>
        <button class="btn primary big" data-act="find">${ICONS.sparkle} Find new creators</button>
      </div>`;
    $("#pager").innerHTML = "";
    return;
  }
  if (S.viewJob) {
    const job = S.job && S.job.id === S.viewJob ? S.job : null;
    const running = job && (job.status === "running" || job.status === "queued");
    $("#results-count").innerHTML = `<b>${data.total}</b> ${data.total === 1 ? "creator" : "creators"} found by this search`
      + ` · <button class="btn link" data-act="show-all">Show all saved creators (${data.library_size})</button>` + downloadLinks(data.total);
    if (!data.items.length) {
      grid.innerHTML = running
        ? `<div class="empty"><h2>Scouting…</h2><p>Creators appear here as they're ranked.</p></div>`
        : `<div class="empty"><h2>No new creators this time</h2><p>This search didn't find new creators that fit${job?.outside ? ` (${job.outside} were outside your markets)` : ""}. Try other creator types, a bigger size range, or another platform.</p>
          <button class="btn" data-act="show-all">Show all saved creators</button></div>`;
    } else {
      grid.innerHTML = data.items.map(cardHtml).join("");
    }
    renderPager(data.page, data.pages);
    return;
  }
  $("#results-count").innerHTML = `<b>${data.total}</b> ${data.total === 1 ? "creator" : "creators"}${filtered ? " match your filters" : ""}`
    + (filtered ? ` · <button class="btn link" data-act="reset-filters">Clear</button>` : "") + downloadLinks(data.total);
  if (!data.items.length) {
    grid.innerHTML = `<div class="empty"><h2>Nothing here yet</h2><p>None of your saved creators match this. Press <b>Find new creators</b> to search the platforms for exactly this, or clear the filters.</p>
      <button class="btn primary" data-act="find">${ICONS.sparkle} Find new creators</button> <button class="btn" data-act="reset-filters">Clear filters</button></div>`;
  } else {
    grid.innerHTML = data.items.map(cardHtml).join("");
  }
  renderPager(data.page, data.pages);
}

// Excel / CSV of exactly what the grid shows (all pages)
function downloadLinks(total) {
  if (!total) return "";
  const qs = queryString({ page: "", page_size: "" });
  const base = `/api/companies/${S.company.id}/export?${qs}`;
  return `<span class="downloads">Download <a class="btn small" href="${base}&format=xlsx" download>Excel</a><a class="btn small" href="${base}&format=csv" download>CSV</a></span>`;
}

function renderPager(page, pages) {
  const el = $("#pager");
  if (pages <= 1) { el.innerHTML = ""; return; }
  const nums = new Set([1, pages, page, page - 1, page + 1, page - 2, page + 2].filter((n) => n >= 1 && n <= pages));
  const sorted = [...nums].sort((a, b) => a - b);
  let html = `<button data-page="${page - 1}" ${page === 1 ? "disabled" : ""} aria-label="Previous page">‹</button>`;
  sorted.forEach((n, i) => {
    if (i && n - sorted[i - 1] > 1) html += '<span class="gap">…</span>';
    html += `<button data-page="${n}" class="${n === page ? "cur" : ""}">${n}</button>`;
  });
  html += `<button data-page="${page + 1}" ${page === pages ? "disabled" : ""} aria-label="Next page">›</button>`;
  el.innerHTML = html;
}

// ---------- Detail ----------
async function openDetail(id) {
  S.detailId = id;
  const dlg = $("#detail");
  dlg.innerHTML = `<div class="loading-line" style="padding:40px"><span class="spinner"></span>Loading…</div>`;
  if (!dlg.open) dlg.showModal();
  try {
    const d = await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}`);
    renderDetail(d);
  } catch (e) {
    dlg.close();
    toast(e.message, "err");
  }
}

function barRow(label, value, hint) {
  return `<div class="barrow" title="${esc(hint)}"><span>${label}</span><div class="track"><i style="width:${value}%"></i></div><b>${value}</b></div>`;
}

function renderDetail({ card: c, creator: cr, match: m }) {
  const dlg = $("#detail");
  const lang = S.meta.languages[m.language] || m.language || "Unknown language";
  const country = S.meta.markets[c.country]?.name || c.country || "Unknown location";
  const tier = S.meta.tiers.find((t) => t.key === cr.tier)?.label;
  const vs = cr.engagement_vs_typical;
  const engHint = cr.platform === "instagram" ? "likes + comments per follower" : "likes + comments per view";
  const starred = m.status && m.status !== "hidden";
  const posts = (cr.recent_posts || []).slice(0, 6);
  const cover = c.cover ? `<img src="${esc(c.cover)}" alt="" data-name="${esc(c.name)}">` : placeholder(c.name);
  S.pitch = m.pitch;

  dlg.innerHTML = `
    <div class="detail">
      <aside>
        <div class="detail-cover">${cover}
          <span class="plat plat-${c.platform}">${ICONS[c.platform]}</span>
        </div>
        <div class="detail-side">
          <button class="btn ${starred ? "dark" : "primary"}" data-act="toggle-shortlist" data-id="${esc(c.id)}" data-status="${esc(m.status || "")}">
            ${starred ? ICONS.starOn + " On shortlist" : ICONS.star + " Add to shortlist"}</button>
          <a class="btn" href="${esc(cr.url)}" target="_blank" rel="noopener">${ICONS.ext} Open ${esc(S.meta.platforms[c.platform])} profile</a>
          <button class="btn link" data-act="toggle-hide" data-id="${esc(c.id)}" data-status="${esc(m.status || "")}">
            ${m.status === "hidden" ? "Unhide this creator" : "Not a fit, hide"}</button>
        </div>
      </aside>
      <div class="detail-main">
        <div class="d-title">
          <div>
            <h2>${esc(c.name)}</h2>
            <div class="d-sub">
              <span>${ICONS[c.platform]} ${esc(cr.handle || "")}</span>
              <span>${esc(country)}</span><span>${esc(lang)}</span>
              ${m.niche ? `<span class="pill">${esc(m.niche)}</span>` : ""}
              ${m.games?.length ? `<span class="pill">🎮 ${esc(m.games.join(", "))}</span>` : ""}
              ${m.hidden_gem ? '<span class="pill gem">💎 Hidden gem</span>' : ""}
              ${cr.verified ? '<span class="pill">Verified</span>' : ""}
            </div>
          </div>
          <div class="bigscore"><b class="${scoreClass(m.score)}">${m.score}</b><span>Match</span></div>
          <button class="x" data-act="close" aria-label="Close">${ICONS.x}</button>
        </div>

        <div class="stats">
          <div class="stat"><b>${fmtNum(cr.followers)}</b><span>${c.platform === "youtube" ? "subscribers" : "followers"}${tier ? " · " + tier : ""}</span></div>
          <div class="stat" title="${esc(`Average views per ${cr.views_basis === "videos, Shorts excluded" ? "video (Shorts excluded)" : "post"}, posts younger than 2 days left out`)}">
            <b>${fmtNum(cr.avg_views)}</b><span>avg views${cr.views_window ? ` · ${esc(cr.views_window)}` : ""}</span></div>
          <div class="stat" title="${esc(engHint)}"><b>${pct(cr.engagement_rate)}</b><span>engagement${vs ? ` · ${vs}× typical` : ""}</span></div>
          <div class="stat" title="Average views in the last 30 days compared with the 60 days before">
            <b class="${cr.views_trend > 0.2 ? "up" : cr.views_trend < -0.2 ? "down" : ""}">${cr.views_trend != null ? `${cr.views_trend > 0 ? "↑" : cr.views_trend < 0 ? "↓" : ""} ${Math.abs(Math.round(cr.views_trend * 100))}%` : "—"}</b>
            <span>views trend${cr.trend ? " · " + esc(cr.trend.toLowerCase()) : ""}</span></div>
        </div>
        <p class="activity">Posts ${cr.posts_per_month ?? "—"} times a month · last post ${daysAgo(cr.days_since_last_post)}${cr.views_basis === "videos, Shorts excluded" ? " · views counted on normal videos, Shorts excluded" : ""}${cr.shorts_share ? ` · ${Math.round(cr.shorts_share * 100)}% of recent uploads are Shorts` : ""}</p>

        <p class="summary">${esc(m.summary)}</p>
        <div class="tagline">${(m.tags || []).map((t) => `<span>${esc(t)}</span>`).join("")}</div>

        <div class="cols">
          <div class="section">
            <h4>Why they fit</h4>
            <ul>${(m.why || []).map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
            ${m.red_flags?.length ? `<h4 style="margin-top:12px">Watch out</h4><ul class="flags">${m.red_flags.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
          </div>
          <div class="section">
            <h4>Score breakdown</h4>
            ${barRow("Niche fit", m.niche_fit, "How closely their recent content matches the creator types you picked (AI)")}
            ${barRow("Market", m.market_fit, "How likely their audience is in your target markets (AI)")}
            ${barRow("Engagement", m.engagement, "Engagement and reach compared with typical accounts of the same size")}
            ${barRow("Activity", m.activity, "How recently and how often they post")}
            ${m.brand_safety < 80 ? barRow("Brand safety", m.brand_safety, "Lower means potential brand-safety concerns") : ""}
          </div>
        </div>

        ${posts.length ? `<div class="section"><h4>Recent posts</h4><div class="posts">
          ${posts.map((p) => `<a class="post" href="${esc(p.url || cr.url)}" target="_blank" rel="noopener" title="${esc(p.title)}">
            ${p.thumb ? `<img src="${esc(p.thumb)}" alt="" loading="lazy">` : `<div class="ptitle">${esc((p.title || "").slice(0, 90))}</div>`}
            <span>${p.views != null ? fmtNum(p.views) + " views" : fmtNum(p.likes) + " likes"}</span></a>`).join("")}
        </div></div>` : ""}

        <div class="section">
          <h4>Contact</h4>
          <div class="contact">
            ${cr.emails?.length ? cr.emails.map((e) => `<code>${esc(e)}</code><button class="btn small" data-act="copy" data-text="${esc(e)}">${ICONS.copy} Copy</button>`).join("")
              : `<span class="muted">No public email found. Message them on ${esc(S.meta.platforms[c.platform])}${cr.links?.length ? " or via their link" : ""}.</span>`}
            ${Object.entries(cr.socials || {}).map(([k, l]) => `<a class="btn small" href="${esc(l)}" target="_blank" rel="noopener">${ICONS[k] || ICONS.ext} ${esc(k[0].toUpperCase() + k.slice(1))}</a>`).join("")}
            ${(cr.links || []).filter((l) => !Object.values(cr.socials || {}).includes(l)).slice(0, 3).map((l) => `<a class="btn small" href="${esc(l)}" target="_blank" rel="noopener">${ICONS.ext} ${esc(l.replace(/^https?:\/\/(www\.)?/, "").slice(0, 32))}</a>`).join("")}
          </div>
        </div>

        <div class="section">
          <h4>Outreach</h4>
          <div id="pitch-area">${m.pitch ? pitchHtml(m.pitch, cr) : `
            <button class="btn primary" data-act="pitch" data-id="${esc(c.id)}">${ICONS.mail} Draft a message in ${esc(lang)}</button>`}
          </div>
        </div>

        ${cr.found_via?.length ? `<p class="via">How we found them: ${cr.found_via.map(esc).join(" · ")}</p>` : ""}
      </div>
    </div>`;
}

function pitchHtml(p, cr) {
  const email = cr.emails?.[0];
  const mailto = email ? `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent(p.subject)}&body=${encodeURIComponent(p.message)}` : "";
  const sameLang = p.english && p.english.trim() === p.message.trim();
  return `<div class="pitch">
    <div class="subject">${esc(p.subject)}</div>
    <textarea id="pitch-text" aria-label="Message">${esc(p.message)}</textarea>
    <div class="actions">
      <button class="btn small primary" data-act="copy-pitch">${ICONS.copy} Copy message</button>
      ${email ? `<a class="btn small" href="${esc(mailto)}">${ICONS.mail} Open in email</a>` : ""}
      ${!sameLang && p.english ? `<button class="btn small" data-act="toggle-english" data-shown="orig">Show English</button>` : ""}
      <button class="btn small" data-act="pitch" data-id="${esc(cr.id)}">Rewrite</button>
    </div>
  </div>`;
}

async function draftPitch(id, button) {
  const area = $("#pitch-area");
  if (button) button.disabled = true;
  area.innerHTML = `<div class="loading-line"><span class="spinner"></span>${esc(S.meta.ai.label)} is writing a personal message…</div>`;
  try {
    const p = await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}/pitch`, { method: "POST" });
    const d = await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}`);
    S.pitch = p;
    area.innerHTML = pitchHtml(p, d.creator);
  } catch (e) {
    area.innerHTML = `<button class="btn primary" data-act="pitch" data-id="${esc(id)}">${ICONS.mail} Try again</button>`;
    toast(e.message, "err");
  }
}

async function setStatus(id, status) {
  await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}`, { method: "PATCH", body: { status } });
  updateShortlistCount();
}

// ---------- Find new creators ----------
// Uses exactly what's picked in the search area; no extra dialog.
function flagRow(id) {
  const row = $(id);
  row.classList.remove("attention");
  void row.offsetWidth; // restart the animation
  row.classList.add("attention");
  setTimeout(() => row.classList.remove("attention"), 1500);
}

async function startFind() {
  const src = S.meta.sources;
  if (!src.ai) { openSettings(); return toast("First choose an AI and add its key", "err"); }
  if (!S.f.markets.length) {
    flagRow("#crit-markets");
    return toast("Pick at least one market to search in", "err");
  }
  const wanted = S.f.platforms.length ? S.f.platforms : Object.keys(S.meta.platforms);
  const usable = wanted.filter((p) => src[p]);
  if (!usable.length) return toast("These platforms aren't set up yet. Add a YouTube key or Apify token in Settings.", "err");
  const skipped = wanted.filter((p) => !src[p]).map((p) => S.meta.platforms[p]);
  const body = {
    ...Object.fromEntries(Object.keys(DEFAULT_SEARCH).map((k) => [k, S.f[k]])),
    platforms: usable,
    focus: S.f.q,
  };
  $("#find-btn").disabled = true;
  try {
    S.job = await api(`/api/companies/${S.company.id}/jobs`, { method: "POST", body });
    S.viewJob = S.job.id;
    S.page = 1;
    loadCreators({ quiet: true });
    if (skipped.length) toast(`Skipping ${skipped.join(" and ")} (no API key yet)`);
    renderJob();
    startPolling();
  } catch (err) {
    toast(err.message, "err");
    $("#find-btn").disabled = false;
  }
}

// ---------- Job progress ----------
function jobProgress(job) {
  if (job.status === "done") return 100;
  const steps = job.steps || [];
  const sources = steps.filter((s) => !["plan", "filter", "score"].includes(s.key));
  const srcDone = sources.length ? sources.filter((s) => s.status !== "running").length / sources.length : 0;
  let p = 4;
  if (steps.find((s) => s.key === "plan")?.status === "done") p = 12;
  p += srcDone * 40;
  if (steps.find((s) => s.key === "filter")?.status === "done") p = 58;
  if (job.to_score) p = 58 + (job.scored / job.to_score) * 42;
  return Math.min(99, Math.round(p));
}

function renderJob() {
  const job = S.job;
  const el = $("#job");
  if (!job) { el.hidden = true; $("#find-btn").disabled = false; return; }
  el.hidden = false;
  const running = job.status === "running" || job.status === "queued";
  $("#find-btn").disabled = running;
  const where = job.markets.map((m) => S.meta.markets[m]?.name || m).join(", ");
  const on = job.platforms.map((p) => S.meta.platforms[p]).join(", ");
  const unscored = job.unscored?.length || 0;
  const title = running ? "Scouting creators…"
    : job.status === "done" ? `Done: ${job.new ?? 0} new creators ranked${unscored ? `, ${unscored} not scored yet` : ""}` : "Search stopped";
  el.innerHTML = `
    <div class="job-top">
      ${running ? '<span class="spinner"></span>' : job.status === "done" ? "✅" : "⚠️"}
      <strong>${esc(title)}</strong>
      <span class="muted">${esc(where)} · ${esc(on)}${job.tags?.length ? ` · ${esc(job.tags.join(", "))}` : ""}${job.focus ? ` · “${esc(job.focus)}”` : ""}</span>
      ${!running && unscored ? `<button class="btn small primary" data-act="retry-scoring">Retry scoring ${unscored}</button>` : ""}
      ${running ? "" : '<button class="btn small" data-act="dismiss-job">Dismiss</button>'}
    </div>
    <div class="bar"><i style="width:${jobProgress(job)}%"></i></div>
    <ol class="steps">${(job.steps || []).map((s) => `<li class="${s.status}" title="${esc(s.detail)}"><span class="dot"></span>${esc(s.label)}${s.detail ? ` <em>· ${esc(s.detail)}</em>` : ""}</li>`).join("")}</ol>
    ${job.error ? `<p style="color:#d33;margin:10px 0 0;font-size:14px">${esc(job.error)}</p>` : ""}`;
}

function startPolling() {
  stopPolling();
  S.polls = 0;
  const tick = async () => {
    if (!S.job) return;
    try { S.job = await api(`/api/jobs/${S.job.id}`); } catch { /* transient */ }
    renderJob();
    const running = S.job.status === "running" || S.job.status === "queued";
    if (running) {
      if (++S.polls % 2 === 0 && S.view === "discover") loadCreators({ quiet: true });
      S.pollTimer = setTimeout(tick, 2000);
    } else {
      S.pollTimer = null;
      loadCreators();
      if (S.job.status === "done" && S.job.unscored?.length) toast(`${S.job.new ?? 0} ranked; ${S.job.unscored.length} couldn't be scored. Press Retry scoring.`, "err");
      else if (S.job.status === "done") toast(`${S.job.new ?? 0} new creators ranked`, "ok");
      else toast(S.job.error || "Search failed", "err");
    }
  };
  S.pollTimer = setTimeout(tick, 1500);
}

function stopPolling() { clearTimeout(S.pollTimer); S.pollTimer = null; }

async function resumeJob() {
  const job = await api(`/api/companies/${S.company.id}/jobs/latest`).catch(() => null);
  if (job && job.status !== "running" && job.status !== "queued" && job.unscored?.length) {
    S.job = job; // finished, but some creators still need scoring: offer the retry
    renderJob();
  } else if (job && (job.status === "running" || job.status === "queued")) {
    S.job = job;
    S.viewJob = job.id;
    renderJob();
    startPolling();
  } else {
    S.job = null;
  }
}

// ---------- Company form ----------
// Only who the company is. What kind of creators to look for is chosen in the search area.
function openCompanyForm(company) {
  const isNew = !company;
  const co = company || { name: "", description: "" };
  const dlg = $("#company");
  dlg.innerHTML = `
    <form method="dialog" id="company-form">
      <div class="dlg-head">
        <div><h2 id="company-title">${isNew ? "Add a company" : `Edit ${esc(co.name)}`}</h2>
        <p>Just tell Scout what the company does. You'll pick creator types and markets in the search.</p></div>
        <button type="button" class="x" data-act="close" aria-label="Close">${ICONS.x}</button>
      </div>
      <div class="dlg-body">
        <label class="field"><span>Company name</span><input type="text" id="co-name" value="${esc(co.name)}" required></label>
        <label class="field"><span>What does the company do?</span>
          <textarea id="co-desc" rows="5" placeholder="e.g. Finnish marketplace for refurbished gaming PCs. Every PC is tested and comes with a warranty, and costs less than buying new. Sells across Europe.">${esc(co.description)}</textarea>
          <small>What you sell, to whom, and what makes it different. The AI uses this to suggest creator types and to judge fit.</small></label>
      </div>
      <div class="dlg-foot">
        ${isNew ? "" : '<button type="button" class="btn link danger" data-act="delete-company">Delete company</button>'}
        <span class="spacer"></span>
        <button type="button" class="btn" data-act="close">Cancel</button>
        <button type="submit" class="btn primary" id="co-save">${isNew ? "Create company" : "Save"}</button>
      </div>
    </form>`;

  dlg.onclick = async (e) => {
    if (e.target.closest("[data-act]")?.dataset.act !== "delete-company") return;
    if (!confirm(`Delete ${co.name} and its creator rankings?`)) return;
    try {
      await api(`/api/companies/${co.id}`, { method: "DELETE" });
      S.companies = await api("/api/companies");
      dlg.close();
      setCompany(S.companies[0]);
    } catch (err) { toast(err.message, "err"); }
  };

  $("#company-form").onsubmit = async (e) => {
    e.preventDefault();
    const body = { name: $("#co-name").value.trim(), description: $("#co-desc").value.trim() };
    if (!body.name) return toast("Give the company a name", "err");
    if (!body.description) return toast("Describe what the company does", "err");
    const btn = $("#co-save");
    btn.disabled = true;
    if (S.meta.sources.ai && (isNew || body.description !== co.description)) {
      btn.innerHTML = `<span class="spinner"></span> Suggesting creator types…`;
    }
    try {
      const saved = isNew ? await api("/api/companies", { method: "POST", body }) : await api(`/api/companies/${co.id}`, { method: "PUT", body });
      S.companies = await api("/api/companies");
      dlg.close();
      toast(isNew ? `${saved.name} added. Pick creator types and markets to search.` : "Saved", "ok");
      setCompany(saved);
    } catch (err) {
      toast(err.message, "err");
      btn.disabled = false;
      btn.textContent = isNew ? "Create company" : "Save";
    }
  };
  dlg.showModal();
  $(isNew ? "#co-name" : "#co-desc").focus();
}

async function suggestTags(button) {
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Thinking…`;
  try {
    const r = await api(`/api/companies/${S.company.id}/suggest-tags`, { method: "POST" });
    S.company.suggested_tags = r.suggested_tags;
    renderTagPicker();
    toast(r.added.length ? `${r.added.length} new ideas added` : "No new ideas this time");
  } catch (err) {
    toast(err.message, "err");
    renderTagPicker();
  }
}

// ---------- Settings (AI choice + API keys) ----------
const DATA_KEY_LINKS = {
  youtube: "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
  apify: "https://console.apify.com/settings/integrations",
};

async function openSettings() {
  let st;
  try { st = await api("/api/settings"); } catch (e) { return toast(e.message, "err"); }
  const dlg = $("#settings");
  let provider = st.ai_provider;
  const drafts = {}; // unsaved edits per provider, so switching back and forth keeps what was typed

  dlg.innerHTML = `
    <form id="settings-form" autocomplete="off">
      <div class="dlg-head">
        <div><h2 id="settings-title">Settings</h2><p>Keys are saved only on this computer and are never shown again in full.</p></div>
        <button type="button" class="x" data-act="close" aria-label="Close">${ICONS.x}</button>
      </div>
      <div class="dlg-body">
        <section class="set-section">
          <h3>AI</h3>
          <p class="muted small">Plans the searches, scores creators and writes messages. Pick any one.</p>
          <div class="provider-grid" id="ai-providers"></div>
          <div id="ai-fields" class="ai-fields"></div>
        </section>
        <section class="set-section">
          <h3>Data sources</h3>
          ${dataKeyField("youtube", "YouTube API key", st.youtube_key_hint, "Free: Google Cloud console → enable YouTube Data API v3 → Credentials → Create API key.")}
          ${dataKeyField("apify", "Apify token (TikTok + Instagram)", st.apify_token_hint, "Free plan includes $5/month: console.apify.com → Settings → API & Integrations.")}
        </section>
      </div>
      <div class="dlg-foot">
        <span class="spacer"></span>
        <button type="button" class="btn" data-act="close">Cancel</button>
        <button type="submit" class="btn primary">Save</button>
      </div>
    </form>`;

  const renderProviders = () => {
    $("#ai-providers").innerHTML = Object.entries(st.providers).map(([k, p]) => `
      <button type="button" class="provider-card ${k === provider ? "on" : ""}" data-provider="${k}" aria-pressed="${k === provider}" aria-label="${esc(p.label)} (${esc(p.company)})${p.ready ? ", set up" : ""}">
        <b>${esc(p.label)}${p.ready ? '<span class="ready" title="Set up">✓</span>' : ""}</b>
        <small>${esc(p.company)}</small>
      </button>`).join("");
  };

  const loaded = {};    // provider -> { models, recommended, manual } once "Load models" ran
  const autoTried = {}; // so a failing auto-load isn't retried on every re-render

  const readFields = () => {
    if (!$("#ai-model")) return;
    const model = $("#ai-model").value.trim();
    drafts[provider] = {
      api_key: $("#ai-key")?.value.trim() || "",
      model: model === "__custom__" ? "" : model,
      base_url: $("#ai-url")?.value.trim() ?? null,
      workspace_id: $("#ai-workspace")?.value.trim() ?? null,
      clear_key: drafts[provider]?.clear_key || false,
    };
  };

  // A real dropdown of every model the key can use (the old type-ahead box hid most of them).
  const modelFieldHtml = (p, model) => {
    const l = loaded[provider];
    if (l && !l.manual) {
      return `<select id="ai-model" class="model-select" aria-label="Model">
        ${l.models.map((m) => `<option value="${esc(m)}" ${m === model ? "selected" : ""}>${esc(m)}${m === l.recommended ? "   ★ recommended" : ""}</option>`).join("")}
        <option value="__custom__">Type a different name…</option></select>`;
    }
    return `<input type="text" id="ai-model" value="${esc(model)}" aria-label="Model"
      placeholder="${esc(p.default_model || "Press Load models, then pick one")}">`;
  };

  const renderFields = () => {
    const p = st.providers[provider];
    const d = drafts[provider] || {};
    let model = d.model ?? p.model;
    const l = loaded[provider];
    if (l && !l.manual && !l.models.includes(model)) model = l.recommended;
    const keyField = p.needs_key || provider === "custom" ? `
      <div class="field"><span>API key${p.needs_key ? "" : ' <span class="muted">(if the server needs one)</span>'}</span>
        <div class="key-row">
          <input type="password" id="ai-key" value="${esc(d.api_key || "")}" autocomplete="new-password"
            placeholder="${p.key_hint && !d.clear_key ? `Saved (${esc(p.key_hint)}). Paste a new key to replace it` : "Paste your key"}">
          ${p.key_url ? `<a class="btn small" href="${esc(p.key_url)}" target="_blank" rel="noopener">${ICONS.ext} Get a key</a>` : ""}
        </div>
        ${p.key_hint && !d.clear_key ? '<button type="button" class="btn link small-link" data-act="clear-ai-key">Remove saved key</button>' : ""}
      </div>` : `<p class="note">No key needed. ${provider === "ollama" ? `Install Ollama, run a model once (for example <code>ollama run ${esc(p.default_model)}</code>), and keep it running. Local models are free but slower and less precise.` : ""}</p>`;
    $("#ai-fields").innerHTML = `
      ${keyField}
      ${p.workspace ? `<div class="field" id="workspace-field"><span>Workspace ID <span class="muted">(only if your key asks for one)</span></span>
        <input type="text" id="ai-workspace" value="${esc(d.workspace_id ?? p.workspace_id ?? "")}" placeholder="wrkspc_…" autocomplete="off" spellcheck="false">
        <small>Organization-wide Claude keys need it. Find it in the Claude Console under Settings → Workspaces, or create the API key inside a workspace instead.</small>
      </div>` : ""}
      ${p.editable_url ? `<div class="field"><span>Address</span>
        <input type="url" id="ai-url" value="${esc(d.base_url ?? p.base_url)}" placeholder="https://your-server/v1"></div>` : ""}
      <div class="field"><span>Model</span>
        <div class="key-row">
          ${modelFieldHtml(p, model)}
          <button type="button" class="btn small" data-act="load-models">${l ? "Reload" : "Load models"}</button>
        </div>
      </div>
      <div class="test-row">
        <button type="button" class="btn small" data-act="test-ai">Test ${esc(p.label)}</button>
        <span class="test-msg" id="ai-test-msg"></span>
      </div>
      ${p.web_search ? "" : `<p class="note">Everything works with ${esc(p.label)}. Only the optional "AI web scout" needs Claude.</p>`}`;
    // A key is already saved: fetch the model list right away so a retired default gets replaced.
    if (!l && !autoTried[provider] && p.needs_key && (p.key_hint || d.api_key) && !d.clear_key) {
      autoTried[provider] = true;
      loadModels();
    }
  };

  const loadModels = async ({ thenTest = false } = {}) => {
    const forProvider = provider;
    const msg = $("#ai-test-msg");
    msg.className = "test-msg";
    msg.textContent = "Loading the models this key can use…";
    const body = aiBody();
    let r;
    try {
      r = await api("/api/settings/models", { method: "POST", body });
    } catch (err) {
      return showResult(msg, { ok: false, message: err.message });
    }
    if (provider !== forProvider) return; // user switched provider meanwhile
    if (!r.ok) return showResult($("#ai-test-msg"), r);
    if (!r.models.length) return showResult($("#ai-test-msg"), { ok: false, message: "No usable models found for this key" });
    loaded[forProvider] = { models: r.models, recommended: r.recommended };
    const wanted = body.model || r.current;
    drafts[forProvider] = { ...drafts[forProvider], model: r.recommended };
    renderFields();
    const note = wanted && wanted !== r.recommended
      ? `“${wanted}” isn't available for this key, so ${r.recommended} was picked instead.`
      : `Using ${r.recommended}.`;
    showResult($("#ai-test-msg"), { ok: true, message: `${r.models.length} models available. ${note}` });
    if (thenTest) await runTest();
  };

  const runTest = async () => {
    const msg = $("#ai-test-msg");
    const btn = $('[data-act="test-ai"]');
    btn.disabled = true;
    msg.className = "test-msg";
    msg.textContent = "Testing…";
    try { showResult(msg, await api("/api/settings/test", { method: "POST", body: aiBody() })); }
    catch (err) { showResult(msg, { ok: false, message: err.message }); }
    finally { btn.disabled = false; }
  };

  // Pasting a key loads the models and tests it straight away.
  let keyLoadedFor = "";
  const keyEntered = (e) => {
    if (e.target.id !== "ai-key") return;
    setTimeout(() => {
      const key = e.target.value.trim();
      if (!key || key === keyLoadedFor) return; // paste and the following change event: load once
      keyLoadedFor = key;
      delete loaded[provider];
      loadModels({ thenTest: true });
    }, 0);
  };
  dlg.onpaste = keyEntered;
  dlg.onchange = (e) => {
    if (e.target.id === "ai-key") return keyEntered(e);
    if (e.target.id === "ai-workspace") {  // new workspace: reload models and test straight away
      delete loaded[provider];
      return loadModels({ thenTest: true });
    }
    if (e.target.id === "ai-model" && e.target.value === "__custom__") {
      readFields();
      loaded[provider].manual = true;
      renderFields();
      $("#ai-model").focus();
    }
  };

  const aiBody = () => {
    readFields();
    const d = drafts[provider] || {};
    return { target: "ai", provider, api_key: d.api_key || null, model: d.model || null, base_url: d.base_url || null,
             workspace_id: d.workspace_id || null };
  };

  const showResult = (el, r) => {
    el.className = `test-msg ${r.ok ? "ok" : "bad"}`;
    el.textContent = (r.ok ? "✓ " : "✗ ") + r.message;
    // Key needs a workspace: point straight at the field that fixes it.
    const ws = $("#workspace-field");
    if (ws) ws.classList.toggle("needs-input", !r.ok && /workspace/i.test(r.message));
    if (ws && !r.ok && /workspace/i.test(r.message)) $("#ai-workspace").focus();
  };

  dlg.onclick = async (e) => {
    const card = e.target.closest("[data-provider]");
    if (card) {
      readFields();
      provider = card.dataset.provider;
      renderProviders();
      renderFields();
      return;
    }
    const act = e.target.closest("[data-act]")?.dataset.act;
    const btn = e.target.closest("button");
    if (act === "clear-ai-key") {
      readFields();
      drafts[provider] = { ...drafts[provider], clear_key: true, api_key: "" };
      renderFields();
    } else if (act === "load-models") {
      btn.disabled = true;
      delete loaded[provider];
      await loadModels();
      const b = $('[data-act="load-models"]');
      if (b) b.disabled = false;
    } else if (act === "test-ai") {
      await runTest();
    } else if (act === "test-youtube" || act === "test-apify") {
      const which = act.slice(5);
      btn.disabled = true;
      const msg = $(`#${which}-msg`);
      msg.className = "test-msg"; msg.textContent = "Testing…";
      const body = { target: which, youtube_api_key: $("#youtube-key").value.trim() || null, apify_token: $("#apify-key").value.trim() || null };
      try { showResult(msg, await api("/api/settings/test", { method: "POST", body })); }
      catch (err) { showResult(msg, { ok: false, message: err.message }); }
      finally { btn.disabled = false; }
    }
  };

  $("#settings-form").onsubmit = async (e) => {
    e.preventDefault();
    readFields();
    const body = {
      ai_provider: provider,
      providers: Object.fromEntries(Object.entries(drafts).map(([k, d]) => [k, {
        api_key: d.api_key || null, model: d.model ?? null, base_url: d.base_url ?? null, clear_key: !!d.clear_key,
        workspace_id: d.workspace_id ?? null,
      }])),
      youtube_api_key: $("#youtube-key").value.trim() || null,
      apify_token: $("#apify-key").value.trim() || null,
    };
    try {
      await api("/api/settings", { method: "PUT", body });
      S.meta = await api("/api/meta");
      renderFilters();
      dlg.close();
      toast(S.meta.ai.ready ? `Saved. Using ${S.meta.ai.label} (${S.meta.ai.model}).` : "Saved", "ok");
    } catch (err) { toast(err.message, "err"); }
  };

  renderProviders();
  renderFields();
  dlg.showModal();
}

function dataKeyField(which, label, hint, help) {
  return `
    <div class="field"><span>${esc(label)}</span>
      <div class="key-row">
        <input type="password" id="${which}-key" autocomplete="new-password"
          placeholder="${hint ? `Saved (${esc(hint)}). Paste a new one to replace it` : "Paste it here"}">
        <a class="btn small" href="${DATA_KEY_LINKS[which]}" target="_blank" rel="noopener">${ICONS.ext} Get one</a>
        <button type="button" class="btn small" data-act="test-${which}">Test</button>
      </div>
      <span class="test-msg" id="${which}-msg"></span>
      <small>${esc(help)}</small>
    </div>`;
}

// ---------- Shortlist ----------
async function updateShortlistCount() {
  if (!S.company) return;
  const data = await api(`/api/companies/${S.company.id}/creators?status=shortlist&page_size=1`).catch(() => null);
  $("#shortlist-count").textContent = data ? data.total : 0;
}

async function renderShortlist() {
  const data = await api(`/api/companies/${S.company.id}/creators?status=shortlist&page_size=500&sort=match`);
  $("#shortlist-count").textContent = data.total;
  $("#export-csv").hidden = !data.total;
  const el = $("#shortlist");
  if (!data.total) {
    el.innerHTML = `<div class="empty"><h2>Your shortlist is empty</h2><p>Open any creator and press <b>Add to shortlist</b>. They'll show up here, ready for outreach.</p>
      <button class="btn primary" data-view="discover">Browse creators</button></div>`;
    return;
  }
  const statuses = [["shortlisted", "Shortlisted"], ["contacted", "Contacted"], ["replied", "Replied"], ["declined", "Declined"]];
  el.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Creator</th><th>Match</th><th>Followers</th><th>Engagement</th><th>Market</th><th>Email</th><th>Status</th></tr></thead>
    <tbody>${data.items.map((c) => `
      <tr>
        <td><div class="who" data-open="${esc(c.id)}">
          ${c.avatar ? `<img src="${esc(c.avatar)}" alt="">` : `<span class="av"></span>`}
          <div><b>${esc(c.name)}</b><small>${ICONS[c.platform]} ${esc(S.meta.platforms[c.platform])}</small></div></div></td>
        <td><span class="mini-score ${scoreClass(c.score)}">${c.score}</span></td>
        <td>${fmtNum(c.followers)}</td>
        <td>${pct(c.engagement_rate)}${c.engagement_vs_typical ? ` <span class="muted">(${c.engagement_vs_typical}×)</span>` : ""}</td>
        <td>${esc(c.country || "—")}</td>
        <td>${c.email ? `<button class="btn small" data-act="copy" data-text="${esc(c.email)}">${ICONS.copy} ${esc(c.email)}</button>` : '<span class="muted">—</span>'}</td>
        <td><select data-status-for="${esc(c.id)}">${statuses.map(([v, l]) => `<option value="${v}" ${c.status === v ? "selected" : ""}>${l}</option>`).join("")}
          <option value="">Remove</option></select></td>
      </tr>`).join("")}</tbody></table></div>`;
}

// ---------- Views ----------
function showView(view) {
  S.view = view;
  $$(".tab").forEach((t) => t.classList.toggle("on", t.dataset.view === view));
  $("#view-discover").hidden = view !== "discover";
  $("#view-shortlist").hidden = view !== "shortlist";
  if (view === "shortlist") renderShortlist();
  else loadCreators();
}

function refresh() {
  if (S.view === "shortlist") renderShortlist();
  else loadCreators();
  updateShortlistCount();
}

// ---------- Events ----------
function bindEvents() {
  $("#q").addEventListener("input", (e) => { S.f.q = e.target.value.trim(); filtersChanged({ debounce: true }); });
  $("#f-sort").addEventListener("change", (e) => { S.f.sort = e.target.value; filtersChanged(); });
  $("#f-language").addEventListener("change", (e) => { S.f.language = e.target.value; filtersChanged(); });
  $("#f-min-score").addEventListener("input", (e) => { S.f.min_score = +e.target.value; $("#min-score-val").textContent = e.target.value; filtersChanged({ debounce: true }); });
  $("#f-min-eng").addEventListener("change", (e) => { S.f.min_eng = +e.target.value; filtersChanged(); });
  $("#f-has-email").addEventListener("change", (e) => { S.f.has_email = e.target.checked; filtersChanged(); });
  $("#f-gems").addEventListener("change", (e) => { S.f.gems = e.target.checked; filtersChanged(); });
  $("#f-hidden").addEventListener("change", (e) => { S.f.show_hidden = e.target.checked; filtersChanged(); });
  $("#c-scout").addEventListener("change", (e) => { S.f.ai_scout = e.target.checked; searchChanged({ reload: false }); });
  $("#size-lo").addEventListener("input", () => sizeFromSlider("lo"));
  $("#size-hi").addEventListener("input", () => sizeFromSlider("hi"));
  $("#toggle-advanced").addEventListener("click", () => {
    const adv = $("#advanced");
    adv.hidden = !adv.hidden;
    $("#toggle-advanced").setAttribute("aria-expanded", String(!adv.hidden));
  });
  $("#company-btn").addEventListener("click", (e) => { e.stopPropagation(); toggleCompanyMenu(); });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && !$("dialog[open]")) {
      e.preventDefault();
      $("#q").focus();
    }
    if ((e.key === "Enter" || e.key === " ") && document.activeElement.classList.contains("card")) {
      e.preventDefault();
      openDetail(document.activeElement.dataset.id);
    }
  });

  // Close dialogs on backdrop click
  $$("dialog").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));
  $("#detail").addEventListener("close", () => { if (S.view === "discover") loadCreators({ quiet: true }); else renderShortlist(); });

  // Images that fail to load become initials
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (img.tagName !== "IMG") return;
    if (img.dataset.name != null) img.outerHTML = placeholder(img.dataset.name);
    else img.style.visibility = "hidden";
  }, true);

  document.addEventListener("change", async (e) => {
    const sel = e.target.closest("select[data-status-for]");
    if (!sel) return;
    try {
      await setStatus(sel.dataset.statusFor, sel.value || null);
      if (!sel.value) renderShortlist();
      toast("Status updated");
    } catch (err) { toast(err.message, "err"); }
  });

  document.addEventListener("click", async (e) => {
    if (!e.target.closest(".company-menu")) toggleCompanyMenu(false);

    const companyBtn = e.target.closest("[data-company]");
    if (companyBtn) {
      const co = S.companies.find((c) => c.id === companyBtn.dataset.company);
      toggleCompanyMenu(false);
      if (co && co.id !== S.company.id) setCompany(co);
      return;
    }
    const viewBtn = e.target.closest("[data-view]");
    if (viewBtn) { showView(viewBtn.dataset.view); return; }
    const pageBtn = e.target.closest("[data-page]");
    if (pageBtn && !pageBtn.disabled) {
      S.page = +pageBtn.dataset.page;
      await loadCreators();
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const sizePreset = e.target.closest("[data-size]");
    if (sizePreset) { const p = SIZE_PRESETS[+sizePreset.dataset.size]; setSize(p.min, p.max); return; }
    const sugg = e.target.closest("[data-sugg]");
    if (sugg) { applySuggestion(S.company.suggested_searches[+sugg.dataset.sugg]); return; }
    const tagAdd = e.target.closest("[data-tag-add]");
    if (tagAdd) { addTag(tagAdd.dataset.tagAdd); return; }
    const tagRemove = e.target.closest("[data-tag-remove]");
    if (tagRemove) {
      S.f.tags = S.f.tags.filter((_, i) => i !== +tagRemove.dataset.tagRemove);
      renderTagPicker();
      searchChanged();
      return;
    }
    const marketRemove = e.target.closest("[data-market-remove]");
    if (marketRemove) {
      S.f.markets = S.f.markets.filter((m) => m !== marketRemove.dataset.marketRemove);
      renderMarketPicker();
      searchChanged();
      return;
    }
    const card = e.target.closest(".card");
    if (card) { openDetail(card.dataset.id); return; }
    const who = e.target.closest("[data-open]");
    if (who) { openDetail(who.dataset.open); return; }

    const actEl = e.target.closest("[data-act]");
    if (!actEl) return;
    const act = actEl.dataset.act;
    if (act === "close") { actEl.closest("dialog")?.close(); }
    else if (act === "go-discover") { e.preventDefault(); showView("discover"); }
    else if (act === "settings") { toggleCompanyMenu(false); openSettings(); }
    else if (act === "find") startFind();
    else if (act === "suggest-tags") suggestTags(actEl);
    else if (act === "reset-filters") {
      // Clear what narrows the grid; keep the settings that only affect new searches.
      const keep = { deal_types: S.f.deal_types, avoid: S.f.avoid, example_creators: S.f.example_creators, ai_scout: S.f.ai_scout };
      S.f = { ...DEFAULT_FILTERS, ...keep };
      $("#q").value = "";
      renderFilters();
      searchChanged();
    }
    else if (act === "new-company") { toggleCompanyMenu(false); openCompanyForm(null); }
    else if (act === "edit-company") { toggleCompanyMenu(false); openCompanyForm(S.company); }
    else if (act === "dismiss-job") { S.job = null; renderJob(); }
    else if (act === "show-all") { S.viewJob = null; S.page = 1; loadCreators(); }
    else if (act === "more-suggestions") moreSuggestions(actEl);
    else if (act === "hide-suggestions" || act === "show-suggestions") {
      try { localStorage.setItem("scout.hideSuggestions", act === "hide-suggestions" ? "1" : "0"); } catch { /* storage blocked */ }
      renderSuggestions();
    }
    else if (act === "retry-scoring") {
      actEl.disabled = true;
      try {
        S.job = await api(`/api/jobs/${S.job.id}/retry-scoring`, { method: "POST" });
        S.viewJob = S.job.id;
        renderJob();
        startPolling();
      } catch (err) { toast(err.message, "err"); actEl.disabled = false; }
    }
    else if (act === "pitch") draftPitch(actEl.dataset.id, actEl);
    else if (act === "copy") { await navigator.clipboard.writeText(actEl.dataset.text); toast("Copied"); }
    else if (act === "copy-pitch") { await navigator.clipboard.writeText($("#pitch-text").value); toast("Message copied"); }
    else if (act === "toggle-english" && S.pitch) {
      const showEnglish = actEl.dataset.shown === "orig";
      $("#pitch-text").value = showEnglish ? S.pitch.english : S.pitch.message;
      actEl.dataset.shown = showEnglish ? "en" : "orig";
      actEl.textContent = showEnglish ? "Show original" : "Show English";
    } else if (act === "toggle-shortlist") {
      const on = actEl.dataset.status && actEl.dataset.status !== "hidden";
      try {
        await setStatus(actEl.dataset.id, on ? null : "shortlisted");
        toast(on ? "Removed from shortlist" : "Added to shortlist", on ? "" : "ok");
        openDetail(actEl.dataset.id);
      } catch (err) { toast(err.message, "err"); }
    } else if (act === "toggle-hide") {
      const hidden = actEl.dataset.status === "hidden";
      try {
        await setStatus(actEl.dataset.id, hidden ? null : "hidden");
        toast(hidden ? "Creator is visible again" : "Hidden from results");
        $("#detail").close();
      } catch (err) { toast(err.message, "err"); }
    }
  });
}

// ---------- Boot ----------
(async function init() {
  bindEvents();
  try {
    [S.meta, S.companies] = await Promise.all([api("/api/meta"), api("/api/companies")]);
  } catch (e) {
    document.body.innerHTML = `<p style="padding:40px">Could not reach the Scout server: ${esc(e.message)}</p>`;
    return;
  }
  let saved = null;
  try { saved = localStorage.getItem("scout.company"); } catch { /* storage blocked */ }
  setCompany(S.companies.find((c) => c.id === saved) || S.companies[0]);
})();
