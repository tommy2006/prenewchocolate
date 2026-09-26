"use strict";

// ---------- Helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, { method = "GET", body } = {}) {
  const raw = body instanceof Blob; // a file upload is sent as-is
  const r = await fetch(path, {
    method,
    headers: body && !raw ? { "Content-Type": "application/json" } : {},
    body: raw ? body : body ? JSON.stringify(body) : undefined,
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
const scoreClass = (s) => (s == null ? "s-none" : s >= 75 ? "s-hi" : s >= 55 ? "s-mid" : "s-lo");
const initials = (name) => (name || "?").replace(/[^\p{L}\p{N} ]/gu, "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
function hue(str) { let h = 0; for (const ch of str || "") h = (h * 31 + ch.charCodeAt(0)) % 360; return h; }
const placeholder = (name) => `<span class="initials" style="background:hsl(${hue(name)} 35% 45%)">${esc(initials(name))}</span>`;
const avatar = (src, name) => (src ? `<img class="av" src="${esc(src)}" alt="" loading="lazy" data-name="${esc(name)}">` : placeholder(name));
const daysAgo = (d) => (d == null ? "—" : d === 0 ? "today" : d === 1 ? "yesterday" : `${d} days ago`);
const trendHtml = (t) => (t == null ? '<span class="muted">—</span>'
  : `<span class="${t >= 0.2 ? "up" : t <= -0.2 ? "down" : "muted"}">${t > 0 ? "↑" : t < 0 ? "↓" : ""}${Math.abs(Math.round(t * 100))}%</span>`);
const euro = (p) => (p ? `€${fmtNum(p.low)}–${fmtNum(p.high)}` : "—");
function ago(iso) {
  const days = Math.floor((Date.now() - new Date(iso)) / 864e5);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

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
  up: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 15 6-6 6 6"/></svg>',
  down: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>',
  chev: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>',
};

function toast(msg, kind = "", action = null) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  if (action) {
    const b = document.createElement("button");
    b.textContent = action.label;
    b.onclick = () => { el.remove(); action.run(); };
    el.append(b);
  }
  $("#toasts").append(el);
  setTimeout(() => el.remove(), kind === "err" ? 6000 : action ? 6000 : 3500);
}

// ---------- State ----------
// Search criteria (saved per company, used for both filtering and new searches)
const DEFAULT_SEARCH = { tags: [], markets: [], platforms: [], tiers: [], follower_min: null, follower_max: null, deal_types: [], avoid: [], example_creators: [], ai_scout: false };
// ...plus filters that only narrow what's already in the library
const DEFAULT_FILTERS = { ...DEFAULT_SEARCH, q: "", language: "", min_score: 0, min_eng: 0, has_email: false, gems: false, growing: false, show_hidden: false, sort: "match" };
const S = {
  meta: null,
  companies: [],
  company: null,
  view: "discover",
  mode: "table",      // table | cards
  f: { ...DEFAULT_FILTERS },
  page: 1,
  rows: [],           // creators on the current page
  cursor: -1,         // keyboard position in `rows`
  selected: new Set(),
  panelId: null,
  panelData: null,
  job: null,
  pollTimer: null,
  polls: 0,
  pitch: null,
  viewJob: null,      // when set, the list shows exactly what that search found
  undo: null,         // filters before the search bar changed them
  recent: null,
};

// ---------- Small controls ----------
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
  return {
    get: () => { const pending = $("input", root).value.trim(); if (pending) add(pending, false); return values; },
    set: (list) => { values = [...list]; render(); changed(); },
  };
}

// Popovers: a button with a sibling .pop. One open at a time; a click outside closes it.
function togglePop(btn, open) {
  const pop = btn.parentElement.querySelector(".pop");
  open = open ?? pop.hidden;
  closePops(pop);
  pop.hidden = !open;
  btn.setAttribute("aria-expanded", String(open));
}
function closePops(except = null) {
  $$(".pop").forEach((p) => {
    if (p === except) return;
    p.hidden = true;
    p.parentElement.querySelector("[aria-expanded]")?.setAttribute("aria-expanded", "false");
  });
  $$(".menu-pop").forEach((m) => m !== except && m.remove());
}

// ---------- Company ----------
function setCompany(company) {
  S.company = company;
  try { localStorage.setItem("scout.company", company.id); } catch { /* storage blocked */ }
  $("#company-name").textContent = company.name;
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
  S.selected.clear();
  S.recent = null;
  S.undo = null;
  $("#q").value = "";
  $("#understood").hidden = true;
  closePanel();
  renderFilters();
  refresh();
  stopPolling();
  $("#job").hidden = true;
  resumeJob();
  if (company.suggesting) waitForSuggestions();
}

function renderCompanyMenu() {
  $("#company-list").innerHTML = S.companies.map((c) => `
      <button data-company="${esc(c.id)}">${esc(c.name)}${c.id === S.company?.id ? '<span class="check-mark">✓</span>' : ""}</button>`).join("")
    + `<div class="sep"></div>
       <button data-act="edit-company">Brand profile: ${esc(S.company?.name || "")}</button>
       <button data-act="new-company">+ Add a company</button>`;
}

function toggleCompanyMenu(open) {
  const menu = $("#company-list");
  open = open ?? menu.hidden;
  if (open) renderCompanyMenu();
  menu.hidden = !open;
  $("#company-btn").setAttribute("aria-expanded", String(open));
}

// ---------- Filter bar ----------
// Creator type, market, platform and size both filter the library and drive "Find new creators".
function renderFilters() {
  const sources = S.meta.sources;
  renderTagPicker();
  renderMarketPicker();
  renderPlatforms();
  renderSize();

  // "More filters": settings for new searches
  chipSelect($("#c-deals"), S.meta.deal_types.map((d) => ({ value: d, label: d })), S.f.deal_types,
    (v) => { S.f.deal_types = v; searchChanged({ reload: false }); });
  chipInput($("#c-avoid"), S.f.avoid, "e.g. Gambling, a competitor…", (v) => { S.f.avoid = v; searchChanged({ reload: false }); });
  chipInput($("#c-examples"), S.f.example_creators, "@handle or profile link", (v) => { S.f.example_creators = v; searchChanged({ reload: false }); });
  $("#c-scout").checked = S.f.ai_scout;

  // "More filters": narrowing the results
  $("#f-language").innerHTML = '<option value="">Any language</option>'
    + Object.entries(S.meta.languages).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#f-language").value = S.f.language;
  $("#f-sort").value = S.f.sort;
  $("#f-min-score").value = S.f.min_score;
  $("#min-score-val").textContent = S.f.min_score;
  $("#f-min-eng").value = String(S.f.min_eng);
  $("#f-has-email").checked = S.f.has_email;
  $("#f-growing").checked = S.f.growing;
  $("#f-gems").checked = S.f.gems;
  $("#f-hidden").checked = S.f.show_hidden;
  updateAdvCount();

  const missing = [];
  if (!sources.ai) missing.push("an AI");
  if (!sources.youtube) missing.push("a YouTube key");
  $("#setup-warning").hidden = !missing.length;
  $("#setup-warning").innerHTML = `<span>Finish setup: add ${missing.join(" and ")}.</span> <button class="btn small" data-act="settings">Open settings</button>`;
  const scoutOk = S.meta.ai.web_search;
  $("#c-scout").disabled = !scoutOk;
  $("#c-scout-note").textContent = scoutOk ? "" : " Needs a Claude key in Settings (as the search or writing AI).";
}

function renderTagPicker() {
  const chosen = S.f.tags;
  $("#c-tags").innerHTML =
    chosen.map((t, i) => `<button type="button" class="chip on" data-tag-remove="${i}" title="Remove">${esc(t)}<span class="x-mark">×</span></button>`).join("")
    + `<span class="pop-anchor"><button type="button" class="chip ghost" id="tag-add-btn" aria-haspopup="true" aria-expanded="false">+ ${chosen.length ? "Add" : "Any type"}</button>
       <div class="pop" id="tag-pop" hidden>${tagPopHtml()}</div></span>`;
}

function tagPopHtml() {
  const lower = S.f.tags.map((t) => t.toLowerCase());
  const ideas = (S.company.suggested_tags || []).filter((t) => !lower.includes(t.toLowerCase()));
  return `<input class="pop-input" id="tag-input" placeholder="Type a creator type, press Enter" aria-label="Add a creator type">
    <div class="chips">${ideas.map((t) => `<button type="button" class="chip" data-tag-add="${esc(t)}">${esc(t)}</button>`).join("")}</div>
    ${S.company.suggesting ? `<p class="hint"><span class="spinner"></span> ${esc(S.meta.ai.label)} is suggesting types…</p>`
      : S.meta.sources.ai ? `<button type="button" class="btn link" data-act="suggest-tags">${ICONS.sparkle} Suggest more types for ${esc(S.company.name)}</button>` : ""}`;
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
    chosen.map((m) => `<button type="button" class="chip on" data-market-remove="${m}" title="Remove">${esc(S.meta.markets[m]?.name || m)}<span class="x-mark">×</span></button>`).join("")
    + `<select class="chip-select" id="market-add" aria-label="Add a market"><option value="">+ ${chosen.length ? "Add" : "All markets"}</option>`
    + rest.map(([k, m]) => `<option value="${k}">${esc(m.name)}</option>`).join("") + `</select>`;
  $("#market-add").addEventListener("change", (e) => {
    if (!e.target.value) return;
    S.f.markets = [...S.f.markets, e.target.value];
    renderMarketPicker();
    searchChanged();
  });
}

function renderPlatforms() {
  const opts = [["", "All"], ...Object.entries(S.meta.search_platforms)];
  const current = S.f.platforms.length === 1 ? S.f.platforms[0] : "";
  $("#f-platforms").innerHTML = opts.map(([k, label]) =>
    `<button type="button" data-platform="${k}" class="${k === current ? "on" : ""}">${k ? ICONS[k] : ""}${esc(label)}</button>`).join("");
}

function updateAdvCount() {
  const n = S.f.deal_types.length + S.f.avoid.length + S.f.example_creators.length + (S.f.ai_scout ? 1 : 0)
    + (S.f.language ? 1 : 0) + (S.f.min_score ? 1 : 0) + (S.f.min_eng ? 1 : 0)
    + (S.f.has_email ? 1 : 0) + (S.f.gems ? 1 : 0) + (S.f.growing ? 1 : 0) + (S.f.show_hidden ? 1 : 0);
  $("#adv-count").hidden = !n;
  $("#adv-count").textContent = n;
}

// ---------- Size ----------
// Slider stops (followers). Index 0 = no minimum, last = no maximum.
const SIZE_STEPS = [0, 1000, 2000, 5000, 10000, 20000, 50000, 100000, 250000, 500000, 1000000, 5000000, null];
const SIZE_PRESETS = [
  { label: "Any size", min: null, max: null },
  { label: "Nano · <10k", min: 1000, max: 10000 },
  { label: "Micro · 10–50k", min: 10000, max: 50000 },
  { label: "Mid · 50–250k", min: 50000, max: 250000 },
  { label: "Macro · 250k+", min: 250000, max: null },
];

function sizeIndex(value, isMax) {
  if (value == null || (!isMax && value === 0)) return isMax ? SIZE_STEPS.length - 1 : 0;
  let best = isMax ? SIZE_STEPS.length - 2 : 1;
  SIZE_STEPS.forEach((s, i) => {
    if (s != null && Math.abs(s - value) < Math.abs((SIZE_STEPS[best] ?? Infinity) - value)) best = i;
  });
  return best;
}

function sizeText(min, max) {
  if (!min && max == null) return "Any size";
  if (max == null) return `${fmtNum(min)}+`;
  if (!min) return `Up to ${fmtNum(max)}`;
  return `${fmtNum(min)}–${fmtNum(max)}`;
}

function renderSize() {
  const lo = sizeIndex(S.f.follower_min, false);
  const hi = sizeIndex(S.f.follower_max, true);
  $("#size-lo").value = lo;
  $("#size-hi").value = hi;
  const last = SIZE_STEPS.length - 1;
  $("#range-fill").style.left = `${(lo / last) * 100}%`;
  $("#range-fill").style.width = `${((hi - lo) / last) * 100}%`;
  $("#size-label").textContent = sizeText(S.f.follower_min, S.f.follower_max) + (S.f.follower_min || S.f.follower_max != null ? " followers" : "");
  $("#size-btn").classList.toggle("on", !!(S.f.follower_min || S.f.follower_max != null));
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

// New companies get their creator types in the background: check back until they're in.
function waitForSuggestions() {
  if (S.suggestTimer) return;
  const id = S.company.id;
  S.suggestTimer = setTimeout(async () => {
    S.suggestTimer = null;
    if (S.company?.id !== id) return;
    try {
      S.companies = await api("/api/companies");
      const fresh = S.companies.find((c) => c.id === id);
      if (!fresh) return;
      S.company = fresh;
      if (!fresh.suggesting) { renderTagPicker(); return; }
    } catch { /* try again */ }
    waitForSuggestions();
  }, 4000);
}

async function suggestTags(button) {
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Thinking…`;
  try {
    const r = await api(`/api/companies/${S.company.id}/suggest-tags`, { method: "POST" });
    S.company.suggested_tags = r.suggested_tags;
    toast(r.added.length ? `${r.added.length} new types` : "No new ideas this time");
  } catch (err) {
    toast(err.message, "err");
  }
  if ($("#tag-pop") && !$("#tag-pop").hidden) $("#tag-pop").innerHTML = tagPopHtml();
}

let saveTimer;
// Search criteria changed: remember them for this company, and refresh the list.
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

// ---------- Search bar: plain words -> filters ----------
const PARSE_KEYS = ["markets", "platforms", "tags", "follower_min", "follower_max", "language", "has_email", "gems", "growing"];

async function runQuery(text) {
  text = text.trim();
  hideRecent();
  if (!text) {
    S.f.q = "";
    $("#understood").hidden = true;
    return filtersChanged();
  }
  S.undo = JSON.parse(JSON.stringify(S.f));
  let r;
  try { r = await api(`/api/companies/${S.company.id}/parse-query`, { method: "POST", body: { q: text, ai: false } }); }
  catch (err) { return toast(err.message, "err"); }
  applyParsed(r, text);
  // What the rules didn't understand: let the AI read it (a local model can take a few seconds).
  if (r.rest && S.meta.sources.ai) {
    showUnderstood(r, text, true);
    try {
      const ai = await api(`/api/companies/${S.company.id}/parse-query`, { method: "POST", body: { q: text, ai: true } });
      if ($("#q").value.trim() === text) applyParsed(ai, text);
    } catch { showUnderstood(r, text, false); }
  }
}

function applyParsed(r, text) {
  const f = r.filters;
  const base = S.undo || S.f;
  S.f = { ...S.f, markets: base.markets, platforms: base.platforms, tags: base.tags };
  if (f.markets) S.f.markets = f.markets;
  if (f.platforms) S.f.platforms = f.platforms.length === Object.keys(S.meta.search_platforms).length ? [] : f.platforms;
  if (f.tags) S.f.tags = f.tags;
  if (f.follower_min !== undefined || f.follower_max !== undefined) {
    S.f.follower_min = f.follower_min || null;
    S.f.follower_max = f.follower_max ?? null;
  }
  if (f.language) S.f.language = f.language;
  if (f.has_email) S.f.has_email = true;
  if (f.gems) S.f.gems = true;
  if (f.growing) S.f.growing = true;
  if (f.engaged) S.f.min_eng = 50;
  S.f.q = r.rest || "";
  renderFilters();
  searchChanged();
  showUnderstood(r, text, false);
}

function showUnderstood(r, text, thinking) {
  const el = $("#understood");
  const parts = [...(r.understood || [])];
  if (r.rest) parts.push(`text “${r.rest}”`);
  el.hidden = false;
  el.innerHTML = (parts.length ? `<span class="muted">Searching for</span> ${parts.map((p) => `<b>${esc(p)}</b>`).join('<span class="dot-sep">·</span>')}` : `<span class="muted">Didn't recognise any filters in “${esc(text)}”.</span>`)
    + (thinking ? ` <span class="thinking"><span class="spinner"></span> ${esc(S.meta.ai.label)} is reading the rest…</span>` : "")
    + (S.undo ? ` <button class="btn link" data-act="undo-query">Undo</button>` : "");
}

async function showRecent() {
  if (!S.company) return;
  if (!S.recent) {
    try { S.recent = await api(`/api/companies/${S.company.id}/recent-searches`); } catch { return; }
  }
  if (!S.recent.length || $("#q").value.trim() || document.activeElement !== $("#q")) return;
  const el = $("#recent");
  el.innerHTML = `<div class="recent-head">Recent searches</div>` + S.recent.map((j, i) => {
    const bits = [j.tags?.join(", "), j.markets.map((m) => S.meta.markets[m]?.name || m).join(", "),
      j.platforms.map((p) => S.meta.platforms[p]).join(" + "), sizeText(j.follower_min, j.follower_max), j.focus && `“${j.focus}”`].filter(Boolean);
    return `<button type="button" data-recent="${i}"><span>${esc(bits.join(" · "))}</span><small>${ago(j.created_at)}${j.new != null ? ` · ${j.new} found` : ""}</small></button>`;
  }).join("");
  el.hidden = false;
}
function hideRecent() { $("#recent").hidden = true; }

function applyRecent(j) {
  S.f.tags = [...(j.tags || [])];
  S.f.markets = [...j.markets];
  S.f.platforms = j.platforms.length === Object.keys(S.meta.search_platforms).length ? [] : [...j.platforms];
  S.f.follower_min = j.follower_min || null;
  S.f.follower_max = j.follower_max ?? null;
  S.f.q = j.focus || "";
  $("#q").value = S.f.q;
  $("#understood").hidden = true;
  hideRecent();
  renderFilters();
  searchChanged();
  toast("Search filled in. Press Find new creators to run it again.");
}

// ---------- Results ----------
function queryString(extra = {}) {
  const f = S.f;
  const p = new URLSearchParams({
    q: f.q, tags: f.tags.join(","), platforms: f.platforms.join(","), tiers: f.tiers.join(","), markets: f.markets.join(","),
    fmin: f.follower_min || 0, fmax: f.follower_max || 0,
    language: f.language, min_score: f.min_score, min_eng: f.min_eng, has_email: f.has_email, gems: f.gems, growing: f.growing,
    status: f.show_hidden ? "hidden" : "", sort: f.sort, page: S.page, page_size: 50, job: S.viewJob || "", ...extra,
  });
  return p.toString();
}

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
  const keep = S.rows[S.cursor]?.id;
  S.rows = data.items;
  S.cursor = keep ? S.rows.findIndex((c) => c.id === keep) : -1;
  renderResults(data);
}

function scoreHtml(value, c, kind) {
  const quick = c.checked === "rules";
  const low = c.confidence === "low";
  const tip = kind === "fit"
    ? `Fit ${value}: would a marketer pick them for ${S.company.name}?`
    : `Audience quality ${value}: is the audience real and paying attention?`;
  const note = quick ? " Quick score from rules; the AI hasn't read their posts yet." : c.checked === "deep" ? " Deep evaluation done." : "";
  return `<span class="sc ${scoreClass(value)}${quick ? " quick" : ""}${low ? " low" : ""}" title="${esc(tip + note + (low ? " Low confidence: little data." : ""))}">${value ?? "—"}</span>`;
}

function badges(c) {
  return [
    c.is_new ? '<span class="tag new">New</span>' : "",
    c.partner ? `<span class="tag partner" title="${esc(`Worked with ${S.company.name} before${c.partner === true ? "" : ` (latest: ${c.partner})`}`)}">Past partner</span>` : "",
    c.hidden_gem ? '<span class="tag gem" title="Small, highly engaged, on-niche and authentic">Gem</span>' : "",
    c.checked === "deep" ? '<span class="tag deep" title="Deep evaluation done">Evaluated</span>' : "",
  ].join("");
}

function rowHtml(c, i) {
  const starred = c.status && c.status !== "hidden";
  const market = [c.country, c.language].filter(Boolean).join(" · ") || "—";
  return `<tr data-id="${esc(c.id)}" data-i="${i}" class="${i === S.cursor ? "cur" : ""} ${S.selected.has(c.id) ? "sel" : ""} ${S.panelId === c.id ? "open" : ""}">
    <td class="c-sel"><input type="checkbox" data-select="${esc(c.id)}" ${S.selected.has(c.id) ? "checked" : ""} aria-label="Select ${esc(c.name)}"></td>
    <td class="c-who"><div class="who">${avatar(c.avatar, c.name)}
      <div class="who-text"><div class="who-name"><span class="plat plat-${c.platform}" title="${esc(S.meta.platforms[c.platform])}">${ICONS[c.platform]}</span><b>${esc(c.name)}</b>${badges(c)}</div>
      <div class="who-sum">${esc(c.summary || c.niche || "")}</div></div></div></td>
    <td class="num">${scoreHtml(c.fit, c, "fit")}</td>
    <td class="num">${scoreHtml(c.quality, c, "quality")}</td>
    <td class="num">${fmtNum(c.followers)}</td>
    <td class="num" title="Median views per post${c.views_window ? `, ${esc(c.views_window)}` : ""}">${fmtNum(c.median_views ?? c.avg_views)}</td>
    <td class="num">${trendHtml(c.views_trend)}</td>
    <td class="c-mkt">${esc(market)}</td>
    <td class="c-icon">${c.has_email ? `<span class="mail" title="${esc(c.email || "Has email")}">${ICONS.mail}</span>` : ""}</td>
    <td class="c-icon"><button class="star ${starred ? "on" : ""}" data-star="${esc(c.id)}" title="${starred ? "On shortlist" : "Add to shortlist"} (s)" aria-label="Shortlist">${starred ? ICONS.starOn : ICONS.star}</button></td>
  </tr>`;
}

function cardHtml(c, i) {
  const starred = c.status && c.status !== "hidden";
  return `<article class="card ${i === S.cursor ? "cur" : ""} ${S.panelId === c.id ? "open" : ""}" data-id="${esc(c.id)}" data-i="${i}" tabindex="0">
    <div class="card-top">${avatar(c.avatar, c.name)}
      <div class="card-id"><b>${esc(c.name)}</b><small><span class="plat plat-${c.platform}">${ICONS[c.platform]}</span>${fmtNum(c.followers)} · ${esc(c.country || "—")}</small></div>
      <button class="star ${starred ? "on" : ""}" data-star="${esc(c.id)}" aria-label="Shortlist">${starred ? ICONS.starOn : ICONS.star}</button></div>
    <div class="card-scores"><span>Fit ${scoreHtml(c.fit, c, "fit")}</span><span>Quality ${scoreHtml(c.quality, c, "quality")}</span>
      <span class="muted">${fmtNum(c.median_views ?? c.avg_views)} views ${trendHtml(c.views_trend)}</span></div>
    <p class="card-sum">${esc(c.summary)}</p>
    <div class="card-tags">${badges(c)}</div>
  </article>`;
}

function renderResults(data) {
  const grid = $("#grid");
  const filtered = S.f.q || S.f.tags.length || S.f.platforms.length || S.f.markets.length || S.f.language || S.f.follower_min || S.f.follower_max != null
    || S.f.min_score || S.f.min_eng || S.f.has_email || S.f.gems || S.f.growing || S.f.show_hidden;
  $("#downloads").innerHTML = downloadLinks(data.total);
  if (!data.library_size) {
    $("#results-count").innerHTML = "";
    grid.innerHTML = `
      <div class="empty">
        <h2>No creators yet for ${esc(S.company.name)}</h2>
        <p>Describe who you want above (or pick types and markets), then press <b>Find new creators</b>. Scout searches YouTube and TikTok in each market's own language and ranks small, genuinely engaged creators first.</p>
      </div>`;
    $("#pager").innerHTML = "";
    return;
  }
  if (S.viewJob) {
    const job = S.job && S.job.id === S.viewJob ? S.job : null;
    const running = job && (job.status === "running" || job.status === "queued");
    $("#results-count").innerHTML = `<b>${data.total}</b> found by this search · <button class="btn link" data-act="show-all">Show all ${data.library_size} saved</button>`;
    if (!data.items.length) {
      grid.innerHTML = running
        ? `<div class="empty"><h2>Scouting…</h2><p>Creators appear here as they're ranked.</p></div>`
        : `<div class="empty"><h2>No new creators this time</h2><p>This search didn't find new creators that fit${job?.outside ? ` (${job.outside} were outside your markets)` : ""}. Try other creator types, a bigger size range, or another platform.</p>
          <button class="btn" data-act="show-all">Show all saved creators</button></div>`;
      $("#pager").innerHTML = "";
      return;
    }
  } else {
    $("#results-count").innerHTML = `<b>${data.total}</b> ${data.total === 1 ? "creator" : "creators"}${filtered ? " match" : ""}`
      + (filtered ? ` · <button class="btn link" data-act="reset-filters">Clear filters</button>` : "");
    if (!data.items.length) {
      grid.innerHTML = `<div class="empty"><h2>Nothing saved matches this</h2><p>Press <b>Find new creators</b> to search the platforms for exactly this, or clear the filters.</p>
        <button class="btn primary" data-act="find">Find new creators</button> <button class="btn" data-act="reset-filters">Clear filters</button></div>`;
      $("#pager").innerHTML = "";
      return;
    }
  }
  if (S.mode === "cards" || window.innerWidth < 700) {  // a table doesn't fit a phone
    grid.className = "cards";
    grid.innerHTML = data.items.map(cardHtml).join("");
  } else {
    grid.className = "";
    const all = data.items.length && data.items.every((c) => S.selected.has(c.id));
    grid.innerHTML = `<div class="table-wrap"><table class="list">
      <thead><tr>
        <th class="c-sel"><input type="checkbox" id="sel-all" ${all ? "checked" : ""} aria-label="Select all on this page"></th>
        <th>Creator</th>
        <th class="num" title="Would a marketer pick them for this brand? Content, audience, market, brand and readiness.">Fit</th>
        <th class="num" title="Is the audience real and paying attention? Authenticity, engagement, consistency, activity, momentum.">Quality</th>
        <th class="num">Followers</th>
        <th class="num" title="Median views per post, last 30 days">Views</th>
        <th class="num" title="Views in the last 30 days vs the 60 before">Trend</th>
        <th>Market</th>
        <th class="c-icon" title="Has a public email">${ICONS.mail}</th>
        <th class="c-icon"></th>
      </tr></thead>
      <tbody>${data.items.map(rowHtml).join("")}</tbody></table></div>`;
  }
  renderPager(data.page, data.pages);
}

// Excel / CSV of exactly what the list shows (all pages)
function downloadLinks(total) {
  if (!total) return "";
  const base = `/api/companies/${S.company.id}/export?${queryString({ page: "", page_size: "" })}`;
  return `<a class="btn small" href="${base}&format=xlsx" download>Excel</a><a class="btn small" href="${base}&format=csv" download>CSV</a>`;
}

function renderPager(page, pages) {
  const el = $("#pager");
  if (pages <= 1) { el.innerHTML = ""; return; }
  const nums = new Set([1, pages, page, page - 1, page + 1].filter((n) => n >= 1 && n <= pages));
  const sorted = [...nums].sort((a, b) => a - b);
  let html = `<button data-page="${page - 1}" ${page === 1 ? "disabled" : ""} aria-label="Previous page">‹</button>`;
  sorted.forEach((n, i) => {
    if (i && n - sorted[i - 1] > 1) html += '<span class="gap">…</span>';
    html += `<button data-page="${n}" class="${n === page ? "cur" : ""}">${n}</button>`;
  });
  html += `<button data-page="${page + 1}" ${page === pages ? "disabled" : ""} aria-label="Next page">›</button>`;
  el.innerHTML = html;
}

// ---------- Selection, bulk actions, keyboard ----------
function toggleSelect(id, on) {
  on = on ?? !S.selected.has(id);
  on ? S.selected.add(id) : S.selected.delete(id);
  $$(`[data-id="${CSS.escape(id)}"]`).forEach((r) => r.classList.toggle("sel", on));
  const box = $(`[data-select="${CSS.escape(id)}"]`);
  if (box) box.checked = on;
  renderBulk();
}

function renderBulk() {
  const n = S.selected.size;
  const bar = $("#bulkbar");
  bar.hidden = !n || S.view !== "discover";
  if (!n) return;
  const ids = [...S.selected].join(",");
  const base = `/api/companies/${S.company.id}/export?ids=${encodeURIComponent(ids)}&status=any`;
  bar.innerHTML = `<b>${n} selected</b>
    <button class="btn small" data-act="bulk-shortlist">${ICONS.star} Shortlist</button>
    <span class="pop-anchor"><button class="btn small" data-act="bulk-hide-menu">Not a fit ${ICONS.chev}</button></span>
    <a class="btn small" href="${base}&format=xlsx" download>Download Excel</a>
    <button class="btn link" data-act="bulk-clear">Clear</button>`;
}

async function bulkStatus(status, reason = "") {
  const ids = [...S.selected];
  try {
    await api(`/api/companies/${S.company.id}/creators/bulk-status`, { method: "POST", body: { ids, status, reason } });
    toast(status === "hidden" ? `${ids.length} hidden` : `${ids.length} added to the shortlist`, "ok");
    S.selected.clear();
    renderBulk();
    loadCreators({ quiet: true });
    updateShortlistCount();
  } catch (err) { toast(err.message, "err"); }
}

function reasonMenu(anchor, onPick) {
  closePops();
  const menu = document.createElement("div");
  menu.className = "menu-pop";
  menu.innerHTML = `<div class="menu-head">Why not a fit? <span class="muted">(the AI learns from it)</span></div>`
    + S.meta.reject_reasons.map((r) => `<button type="button" data-reason="${esc(r)}">${esc(r)}</button>`).join("")
    + `<button type="button" data-reason="" class="muted">Skip reason</button>`;
  const host = anchor.closest(".pop-anchor, .p-actions, .bulkbar") || document.body;
  host.append(menu);
  if (host.classList.contains("p-actions")) menu.style.left = `${anchor.offsetLeft}px`;
  menu.onclick = (e) => {
    const b = e.target.closest("[data-reason]");
    if (!b) return;
    e.stopPropagation();
    menu.remove();
    onPick(b.dataset.reason);
  };
  $("button", menu)?.focus();
}

function moveCursor(delta) {
  if (!S.rows.length) return;
  S.cursor = Math.max(0, Math.min(S.rows.length - 1, (S.cursor < 0 ? (delta > 0 ? -1 : 0) : S.cursor) + delta));
  markCursor();
  if (S.panelId) openPanel(S.rows[S.cursor].id);
}

function markCursor() {
  $$("#grid [data-i]").forEach((el) => el.classList.toggle("cur", +el.dataset.i === S.cursor));
  $(`#grid [data-i="${S.cursor}"]`)?.scrollIntoView({ block: "nearest" });
}

async function toggleStar(id) {
  const c = S.rows.find((r) => r.id === id) || (S.panelData?.card.id === id ? S.panelData.card : null);
  const on = c && c.status && c.status !== "hidden";
  try {
    await setStatus(id, on ? null : "shortlisted");
    toast(on ? "Removed from shortlist" : "Added to shortlist", on ? "" : "ok");
    if (S.view === "shortlist") renderShortlist(); else loadCreators({ quiet: true });
    if (S.panelId === id) openPanel(id);
  } catch (err) { toast(err.message, "err"); }
}

async function hideCreator(id, reason) {
  try {
    await setStatus(id, "hidden", reason);
    toast("Hidden: not a fit" + (reason ? ` (${reason.toLowerCase()})` : ""), "", { label: "Undo", run: async () => { await setStatus(id, null); loadCreators({ quiet: true }); } });
    const i = S.rows.findIndex((r) => r.id === id);
    await loadCreators({ quiet: true });
    if (S.panelId === id) {
      const next = S.rows[Math.min(i, S.rows.length - 1)];
      if (next) { S.cursor = S.rows.indexOf(next); markCursor(); openPanel(next.id); } else closePanel();
    }
  } catch (err) { toast(err.message, "err"); }
}

async function setStatus(id, status, reason = "") {
  await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}`, { method: "PATCH", body: { status, reason } });
  updateShortlistCount();
}

// ---------- Creator panel ----------
async function openPanel(id) {
  S.panelId = id;
  const panel = $("#panel");
  panel.hidden = false;
  document.body.classList.add("with-panel");
  $$("#grid [data-id]").forEach((el) => el.classList.toggle("open", el.dataset.id === id));
  if (!S.panelData || S.panelData.card.id !== id) panel.innerHTML = `<div class="loading-line" style="padding:32px"><span class="spinner"></span>Loading…</div>`;
  try {
    const d = await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}`);
    if (S.panelId !== id) return; // moved on meanwhile
    renderPanel(d);
  } catch (e) {
    closePanel();
    toast(e.message, "err");
  }
}

function closePanel() {
  S.panelId = null;
  S.panelData = null;
  $("#panel").hidden = true;
  document.body.classList.remove("with-panel");
  $$("#grid [data-id].open").forEach((el) => el.classList.remove("open"));
}

function claimHtml(e) {
  const cites = (e.posts || []).map((p) => `<a href="${esc(p.url)}" target="_blank" rel="noopener" title="Open this post">${esc(p.title || "post")}</a>`).join("");
  const quotes = (e.quotes || []).map((q) => `<q>${esc(q)}</q>`).join("");
  return `<li class="${e.sign === "-" ? "minus" : "plus"}"><span class="sign">${e.sign === "-" ? "−" : "+"}</span>
    <div>${esc(e.text)}${cites ? `<div class="cites">${cites}</div>` : ""}${quotes}</div></li>`;
}

function barHtml(value) {
  return `<div class="track"><i class="${scoreClass(value)}" style="width:${value}%"></i></div>`;
}

function renderPanel(d) {
  S.panelData = d;
  const { card: c, creator: cr, match: m, linked = [], partner, agency } = d;
  const lang = S.meta.languages[m.language] || m.language || "";
  const country = S.meta.markets[c.country]?.name || c.country || "";
  const starred = m.status && m.status !== "hidden";
  const auth = cr.authenticity || {};
  const aud = cr.audience || {};
  const conf = m.confidence || { level: "low", notes: [] };
  const ev = m.evidence || [];
  const posts = (cr.recent_posts || []).slice(0, 6);
  S.pitch = m.pitch;
  const i = S.rows.findIndex((r) => r.id === c.id);

  const dims = Object.entries(S.meta.fit_parts).map(([k, label]) => {
    const v = m.fit_parts?.[k] ?? 0;
    const claims = ev.filter((e) => e.dim === k);
    return `<div class="dim"><div class="dim-head"><span>${esc(label)}</span>${barHtml(v)}<b>${v}</b></div>
      ${claims.length ? `<ul class="claims">${claims.map(claimHtml).join("")}</ul>` : ""}</div>`;
  }).join("");

  const qparts = Object.entries(S.meta.quality_parts).map(([k, label]) => {
    const v = m.quality_parts?.[k] ?? 0;
    return `<div class="qpart"><span>${esc(label)}</span>${barHtml(v)}<b>${v}</b></div>`;
  }).join("");
  const signals = (auth.signals || []).map((s) => `<li class="${s.kind === "good" ? "plus" : "minus"}"><span class="sign">${s.kind === "good" ? "✓" : "!"}</span><div>${esc(s.text)}</div></li>`).join("");
  const langs = Object.entries(aud.languages || {}).map(([k, v]) => `${esc(S.meta.languages[k] || k)} ${Math.round(v * 100)}%`).join(" · ");
  const consistency = cr.consistency != null ? `${Math.round(cr.consistency * 100)}% of recent posts reach at least half their average views${cr.views_spread >= 2 ? " (the average is carried by a few hits)" : ""}` : "";

  $("#panel").innerHTML = `
    <div class="p-head">
      ${avatar(c.avatar, c.name)}
      <div class="p-title">
        <h2>${esc(c.name)}</h2>
        <div class="p-sub"><span class="plat plat-${c.platform}">${ICONS[c.platform]}</span><a href="${esc(cr.url)}" target="_blank" rel="noopener">${esc(cr.handle || S.meta.platforms[c.platform])}</a>
          ${country ? `<span>${esc(country)}</span>` : ""}${lang ? `<span>${esc(lang)}</span>` : ""}<span>${fmtNum(cr.followers)} ${c.platform === "youtube" ? "subscribers" : "followers"}</span></div>
        <div class="p-badges">${badges(c)}${partner ? `<span class="tag partner">Worked with you${partner.weeks.length ? ": " + esc(partner.weeks.join(", ")) : ""}</span>` : ""}${m.status === "hidden" ? '<span class="tag">Hidden</span>' : ""}</div>
      </div>
      <div class="p-nav">
        <button class="icon-btn small" data-act="panel-prev" ${i <= 0 ? "disabled" : ""} title="Previous (↑)">${ICONS.up}</button>
        <button class="icon-btn small" data-act="panel-next" ${i < 0 || i >= S.rows.length - 1 ? "disabled" : ""} title="Next (↓)">${ICONS.down}</button>
        <button class="icon-btn small" data-act="panel-close" title="Close (Esc)">${ICONS.x}</button>
      </div>
    </div>
    <div class="p-actions">
      <button class="btn small ${starred ? "dark" : "primary"}" data-act="panel-star">${starred ? ICONS.starOn + " On shortlist" : ICONS.star + " Shortlist"}</button>
      ${m.status === "hidden" ? `<button class="btn small" data-act="panel-unhide">Unhide</button>` : `<button class="btn small" data-act="panel-hide">Not a fit ${ICONS.chev}</button>`}
      <a class="btn small" href="${esc(cr.url)}" target="_blank" rel="noopener">${ICONS.ext} Profile</a>
      <span class="spacer"></span>
      ${S.meta.sources.ai ? `<button class="btn small ${m.checked === "deep" ? "" : "accent"}" data-act="deep" title="Reads their posts, descriptions and viewer comments, and judges fit like a marketer (uses the writing AI)">${ICONS.sparkle} ${m.checked === "deep" ? "Re-evaluate" : "Deep evaluation"}</button>` : ""}
    </div>
    <div class="p-body">
      ${m.verdict ? `<p class="verdict">${esc(m.verdict)}</p>` : `<p class="p-summary">${esc(m.summary)}</p>`}
      ${m.audience_note || m.collab_idea ? `<dl class="deep-notes">
        ${m.audience_note ? `<dt>Audience</dt><dd>${esc(m.audience_note)}</dd>` : ""}
        ${m.collab_idea ? `<dt>Idea</dt><dd>${esc(m.collab_idea)}</dd>` : ""}
        ${m.deep?.sponsors_seen?.length ? `<dt>Sponsors</dt><dd>${esc(m.deep.sponsors_seen.join(", "))}</dd>` : ""}</dl>` : ""}

      <div class="scores">
        <div class="scorebox"><b class="${scoreClass(m.fit)}">${m.fit}</b><div><strong>Fit</strong><small>Would a marketer pick them for ${esc(S.company.name)}?</small></div></div>
        <div class="scorebox"><b class="${scoreClass(m.quality)}">${m.quality}</b><div><strong>Audience quality</strong><small>Is the audience real and paying attention?</small></div></div>
      </div>
      <p class="conf conf-${conf.level}"><span class="dotc"></span>Confidence: <b>${esc(conf.level)}</b>${conf.notes.length ? ` · ${esc(conf.notes.join(" · "))}` : ""}
        ${m.checked === "rules" && S.meta.sources.ai ? ` <button class="btn link" data-act="ai-check">Check with ${esc(S.meta.ai.label)}</button>` : ""}</p>

      <section><h4>Why this fit <span class="muted">· evidence from their posts and comments</span></h4>${dims}</section>

      <section><h4>Audience quality</h4>
        <div class="qparts">${qparts}</div>
        ${signals ? `<ul class="claims signals">${signals}</ul>` : `<p class="muted small">No warning signs in the numbers we have.</p>`}
        ${langs ? `<p class="small">Comment languages (${aud.sampled} sampled): ${langs}</p>` : ""}
        ${consistency ? `<p class="small">${esc(consistency)}</p>` : ""}
      </section>

      <section><h4>Numbers</h4>
        <div class="nums">
          <div><b>${fmtNum(cr.median_views ?? cr.avg_views)}</b><span>median views${cr.views_window ? ` · ${esc(cr.views_window)}` : ""}</span></div>
          <div><b>${pct(cr.engagement_rate)}</b><span>engagement${cr.engagement_vs_typical ? ` · ${cr.engagement_vs_typical}× typical` : ""}</span></div>
          <div><b>${trendHtml(cr.views_trend)}</b><span>views trend</span></div>
          <div><b>${cr.posts_per_month ?? "—"}</b><span>posts / month · last post ${daysAgo(cr.days_since_last_post)}</span></div>
          <div><b>${euro(cr.price)}</b><span>est. price per post</span></div>
          <div><b>${fmtNum(cr.avg_views)}</b><span>average views</span></div>
        </div>
        ${linked.length ? `<div class="also">${linked.map((o) => `<a href="${esc(o.url)}" target="_blank" rel="noopener">${ICONS[o.platform]} Also on ${esc(S.meta.platforms[o.platform])}: ${fmtNum(o.followers)}${o.avg_views != null ? ` · ${fmtNum(o.avg_views)} views` : ""}</a>`).join("")}</div>` : ""}
      </section>

      ${posts.length ? `<section><h4>Recent posts</h4><ul class="postlist">
        ${posts.map((p, k) => `<li><a href="${esc(p.url || cr.url)}" target="_blank" rel="noopener"><span class="pref">p${k + 1}</span><span class="ptitle">${esc(p.title || "(no title)")}</span>
          <span class="pviews">${p.views != null ? fmtNum(p.views) + " views" : fmtNum(p.likes) + " likes"}</span></a></li>`).join("")}</ul></section>` : ""}

      <section><h4>Contact</h4>
        <div class="contact">
          ${cr.emails?.length ? cr.emails.map((e) => `<code>${esc(e)}</code><button class="btn small" data-act="copy" data-text="${esc(e)}">${ICONS.copy} Copy</button>`).join("")
            : `<span class="muted small">No public email. Message them on ${esc(S.meta.platforms[c.platform])}${cr.links?.length ? " or via their link" : ""}.</span>`}
          ${agency ? `<span class="tag" title="A company email that isn't the creator's own, or management mentioned in their bio">Likely via agency</span>` : ""}
          ${Object.entries(cr.socials || {}).map(([k, l]) => `<a class="btn small" href="${esc(l)}" target="_blank" rel="noopener">${ICONS[k] || ICONS.ext} ${esc(k[0].toUpperCase() + k.slice(1))}</a>`).join("")}
        </div>
      </section>

      <section><h4>Outreach</h4>
        <div id="pitch-area">${m.pitch ? pitchHtml(m.pitch, cr) : `<button class="btn small" data-act="pitch">${ICONS.mail} Draft a message in ${esc(lang || "their language")}</button>`}</div>
      </section>

      ${cr.found_via?.length ? `<p class="via">Found via ${cr.found_via.map(esc).join(" · ")}</p>` : ""}
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
      <button class="btn small primary" data-act="copy-pitch">${ICONS.copy} Copy</button>
      ${email ? `<a class="btn small" href="${esc(mailto)}">${ICONS.mail} Open in email</a>` : ""}
      ${!sameLang && p.english ? `<button class="btn small" data-act="toggle-english" data-shown="orig">Show English</button>` : ""}
      <button class="btn small" data-act="pitch">Rewrite</button>
    </div>
  </div>`;
}

async function draftPitch() {
  const id = S.panelId;
  const area = $("#pitch-area");
  area.innerHTML = `<div class="loading-line"><span class="spinner"></span>${esc(S.meta.ai.writer.label)} is writing a personal message…</div>`;
  try {
    const p = await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}/pitch`, { method: "POST" });
    S.pitch = p;
    if (S.panelId === id) $("#pitch-area").innerHTML = pitchHtml(p, S.panelData.creator);
  } catch (e) {
    if (S.panelId === id) $("#pitch-area").innerHTML = `<button class="btn small" data-act="pitch">${ICONS.mail} Try again</button>`;
    toast(e.message, "err");
  }
}

async function rescoreOne(kind, btn) {
  const id = S.panelId;
  btn.disabled = true;
  btn.innerHTML = kind === "deep"
    ? `<span class="spinner"></span> Reading posts and comments…`
    : `<span class="spinner"></span> ${esc(S.meta.ai.label)} is reading their posts…`;
  try {
    await api(`/api/companies/${S.company.id}/creators/${encodeURIComponent(id)}/${kind === "deep" ? "deep" : "ai-check"}`, { method: "POST" });
    if (S.panelId === id) await openPanel(id);
    loadCreators({ quiet: true });
    if (kind === "deep") toast("Deep evaluation done", "ok");
  } catch (err) {
    toast(err.message, "err");
    btn.disabled = false;
    btn.textContent = "Try again";
  }
}

// ---------- Find new creators ----------
function flagRow(id) {
  const row = $(id);
  row.classList.remove("attention");
  void row.offsetWidth; // restart the animation
  row.classList.add("attention");
  setTimeout(() => row.classList.remove("attention"), 1500);
}

async function startFind() {
  const src = S.meta.sources;
  if (!src.ai) { openSettings(); return toast("First choose an AI in Settings", "err"); }
  if (!S.f.markets.length) {
    flagRow("#crit-markets");
    return toast("Pick at least one market to search in", "err");
  }
  const wanted = S.f.platforms.length ? S.f.platforms : Object.keys(S.meta.search_platforms);
  const usable = wanted.filter((p) => src[p]);
  if (!usable.length) return toast("YouTube isn't set up yet. Add a YouTube key in Settings, or search TikTok.", "err");
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
    S.recent = null;
    loadCreators({ quiet: true });
    if (skipped.length) toast(`Skipping ${skipped.join(" and ")} (no API key yet)`);
    renderJob();
    startPolling();
  } catch (err) {
    toast(err.message, "err");
    $("#find-btn").disabled = false;
  }
}

function jobProgress(job) {
  if (job.status === "done") return 100;
  const steps = job.steps || [];
  const sources = steps.filter((s) => !["plan", "filter", "comments", "rules", "score", "link"].includes(s.key));
  const srcDone = sources.length ? sources.filter((s) => s.status !== "running").length / sources.length : 0;
  let p = 4;
  if (steps.find((s) => s.key === "plan")?.status === "done") p = 12;
  p += srcDone * 40;
  if (steps.find((s) => s.key === "filter")?.status === "done") p = 56;
  if (steps.find((s) => s.key === "comments")?.status === "done") p = 60;
  if (job.to_score) p = 60 + (job.scored / job.to_score) * 40;
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
  const current = (job.steps || []).filter((s) => s.status === "running").map((s) => s.label).join(" · ");
  const title = running ? (current || "Starting…")
    : job.status === "done" ? `Done: ${job.new ?? 0} new creators ranked${unscored ? ` (${unscored} with a quick score only)` : ""}`
    : job.status === "stopped" ? `Stopped: ${job.new ?? 0} creators ranked before you stopped` : "Search stopped";
  const open = el.querySelector("details")?.open;
  el.innerHTML = `
    <div class="job-top">
      ${running ? '<span class="spinner"></span>' : `<span class="jdot ${job.status}"></span>`}
      <strong>${esc(title)}</strong>
      <span class="muted">${esc(where)} · ${esc(on)}${job.tags?.length ? ` · ${esc(job.tags.join(", "))}` : ""}${job.focus ? ` · “${esc(job.focus)}”` : ""}</span>
      <span class="spacer"></span>
      ${!running && unscored && S.meta.sources.ai ? `<button class="btn small" data-act="retry-scoring" title="Let the search AI read their posts and re-score them">Check ${Math.min(unscored, S.meta.ai.local ? 10 : 40)} more with AI</button>` : ""}
      ${running ? `<button class="btn small" data-act="stop-job">Stop</button>` : '<button class="btn small" data-act="dismiss-job">Dismiss</button>'}
    </div>
    <div class="bar"><i style="width:${jobProgress(job)}%"></i></div>
    <details ${open ? "open" : ""}><summary>Details</summary>
      <ol class="steps">${(job.steps || []).map((s) => `<li class="${s.status}"><span class="dot"></span>${esc(s.label)}${s.detail ? ` <em>· ${esc(s.detail)}</em>` : ""}</li>`).join("")}</ol>
    </details>
    ${job.error ? `<p class="err-line">${esc(job.error)}</p>` : ""}`;
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
      if (S.job.status === "done") toast(`${S.job.new ?? 0} new creators ranked`, "ok");
      else if (S.job.status === "stopped") toast(`Search stopped. ${S.job.new ?? 0} creators were ranked before that.`);
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

// ---------- Brand profile ----------
// Who the company is and who it wants to reach. The AI judges fit against this.
function openCompanyForm(company) {
  const isNew = !company;
  const co = company || { name: "", description: "", profile: {} };
  const p = { goal: "balanced", competitors: [], no_go: [], ...(co.profile || {}) };
  const dlg = $("#company");
  dlg.innerHTML = `
    <form method="dialog" id="company-form">
      <div class="dlg-head">
        <div><h2 id="company-title">${isNew ? "Add a company" : `Brand profile: ${esc(co.name)}`}</h2>
        <p>The AI judges every creator's fit against this. Only the name and description are required.</p></div>
        <button type="button" class="x" data-act="close" aria-label="Close">${ICONS.x}</button>
      </div>
      <div class="dlg-body form-grid">
        <label class="field"><span>Company name</span><input type="text" id="co-name" value="${esc(co.name)}" required></label>
        <div class="field"><span>Website <em class="opt">optional</em></span>
          <div class="key-row"><input type="url" id="co-website" value="${esc(p.website || "")}" placeholder="https://…">
          <button type="button" class="btn small" data-act="from-website" ${S.meta.sources.ai ? "" : "disabled title='Set up an AI first'"}>${ICONS.sparkle} Fill from website</button></div></div>
        <label class="field span2"><span>What does the company do?</span>
          <textarea id="co-desc" rows="3" placeholder="e.g. Finnish marketplace for refurbished gaming PCs. Every PC is tested and comes with a warranty, and costs less than buying new.">${esc(co.description)}</textarea></label>
        <label class="field span2"><span>Target customer <em class="opt">who buys, and who watches</em></span>
          <textarea id="co-target" rows="2" placeholder="e.g. Gamers 16–35 who want a capable PC for less; parents buying a first gaming PC">${esc(p.target_customer || "")}</textarea></label>
        <div class="field"><span>Campaign goal</span>
          <div class="seg" id="co-goal">${Object.entries(S.meta.goals).map(([k, label]) => `<button type="button" data-goal="${k}" class="${k === p.goal ? "on" : ""}">${esc(label)}</button>`).join("")}</div>
          <small>Sales weighs audience fit most; Awareness weighs reach and audience quality more.</small></div>
        <label class="field"><span>Youngest audience age <em class="opt">optional</em></span>
          <input type="number" id="co-age" min="0" max="99" value="${p.min_audience_age ?? ""}" placeholder="e.g. 13">
          <small>Creators whose viewers are clearly younger rank lower.</small></label>
        <label class="field"><span>Price range <em class="opt">optional</em></span><input type="text" id="co-price" value="${esc(p.price_range || "")}" placeholder="e.g. €500–1,500"></label>
        <label class="field"><span>Budget per collaboration, € <em class="opt">optional</em></span><input type="number" id="co-budget" min="0" step="50" value="${p.budget_max ?? ""}" placeholder="e.g. 800">
          <small>Compared with each creator's estimated price.</small></label>
        <div class="field span2"><span>Competitors <em class="opt">creators they sponsor are flagged</em></span><div class="chip-input" id="co-competitors"></div></div>
        <label class="field span2"><span>Values and tone <em class="opt">optional</em></span><input type="text" id="co-values" value="${esc(p.values || "")}" placeholder="e.g. Trustworthy, value for money, less e-waste"></label>
        <div class="field span2"><span>Never work with <em class="opt">optional</em></span><div class="chip-input" id="co-nogo"></div></div>
        ${isNew ? "" : `<div class="field span2"><span>Past collaborations <em class="opt">optional</em></span>
          <div class="partners-box" id="partners-box">${partnersHtml(co.partners)}</div>
          <input type="file" id="partners-file" accept=".xlsx,.xlsm,.csv" hidden>
          <small>Upload your collaboration tracker (Excel or CSV). Scout marks past partners, fills Agency and Year-week in downloads, and shows the AI what has worked for you.</small>
          <div id="recall-box"></div></div>`}
      </div>
      <div class="dlg-foot">
        ${isNew ? "" : '<button type="button" class="btn link danger" data-act="delete-company">Delete company</button>'}
        <span class="spacer"></span>
        <button type="button" class="btn" data-act="close">Cancel</button>
        <button type="submit" class="btn primary" id="co-save">${isNew ? "Create company" : "Save"}</button>
      </div>
    </form>`;
  const competitors = chipInput($("#co-competitors"), p.competitors, "Company name, press Enter");
  const nogo = chipInput($("#co-nogo"), p.no_go, "e.g. Gambling, adult content");
  let goal = p.goal;

  dlg.onclick = async (e) => {
    const g = e.target.closest("[data-goal]");
    if (g) {
      goal = g.dataset.goal;
      $$("#co-goal button").forEach((b) => b.classList.toggle("on", b === g));
      return;
    }
    const act = e.target.closest("[data-act]")?.dataset.act;
    if (act === "partners-upload") return $("#partners-file").click();
    if (act === "partners-remove") return removePartners(co);
    if (act === "from-website") return fillFromWebsite(e.target.closest("button"), competitors, nogo, (g2) => {
      goal = g2;
      $$("#co-goal button").forEach((b) => b.classList.toggle("on", b.dataset.goal === g2));
    });
    if (act !== "delete-company") return;
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
    const num = (id) => (($(id).value || "").trim() ? Math.max(0, parseInt($(id).value, 10) || 0) || null : null);
    const body = {
      name: $("#co-name").value.trim(),
      description: $("#co-desc").value.trim(),
      profile: {
        website: $("#co-website").value.trim(), target_customer: $("#co-target").value.trim(),
        min_audience_age: num("#co-age"), price_range: $("#co-price").value.trim(), competitors: competitors.get(),
        values: $("#co-values").value.trim(), no_go: nogo.get(), budget_max: num("#co-budget"), goal,
      },
    };
    if (!body.name) return toast("Give the company a name", "err");
    if (!body.description) return toast("Describe what the company does", "err");
    const btn = $("#co-save");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Saving…`;
    try {
      const saved = isNew ? await api("/api/companies", { method: "POST", body }) : await api(`/api/companies/${co.id}`, { method: "PUT", body });
      S.companies = await api("/api/companies");
      dlg.close();
      toast(isNew ? `${saved.name} added. Describe who you want, or pick types and markets.` : "Saved. Rankings updated.", "ok");
      setCompany(saved);
    } catch (err) {
      toast(err.message, "err");
      btn.disabled = false;
      btn.textContent = isNew ? "Create company" : "Save";
    }
  };
  if (!isNew) {
    $("#partners-file").onchange = (e) => uploadPartners(co, e.target);
    if (co.partners) loadRecall(co);
  }
  dlg.showModal();
  $(isNew ? "#co-name" : "#co-desc").focus();
}

async function fillFromWebsite(btn, competitors, nogo, setGoal) {
  const url = $("#co-website").value.trim();
  if (!url) { $("#co-website").focus(); return toast("Enter the website address first", "err"); }
  btn.disabled = true;
  const label = btn.innerHTML;
  btn.innerHTML = `<span class="spinner"></span> Reading…`;
  try {
    const r = await api("/api/profile-from-website", { method: "POST", body: { url, name: $("#co-name").value.trim() } });
    let n = 0;
    const fill = (id, v) => { if (v && !$(id).value.trim()) { $(id).value = v; n++; } };
    fill("#co-desc", r.description);
    fill("#co-target", r.target_customer);
    fill("#co-price", r.price_range);
    fill("#co-values", r.values);
    if (r.min_audience_age && !$("#co-age").value) { $("#co-age").value = r.min_audience_age; n++; }
    if (r.competitors?.length && !competitors.get().length) { competitors.set(r.competitors); n++; }
    if (r.no_go?.length && !nogo.get().length) { nogo.set(r.no_go); n++; }
    if (r.goal) setGoal(r.goal);
    toast(n ? `Filled ${n} fields from the website. Check them before saving.` : "Nothing new found: your fields are already filled.", "ok");
  } catch (err) { toast(err.message, "err"); }
  btn.disabled = false;
  btn.innerHTML = label;
}

function partnersHtml(p) {
  if (!p) return `<button type="button" class="btn small" data-act="partners-upload">Upload Excel or CSV</button>`;
  return `<span><b>${p.count} creators</b>, ${p.collabs} collaborations · ${esc(p.file)}</span>
    <button type="button" class="btn small" data-act="partners-upload">Replace</button>
    <button type="button" class="btn small link danger" data-act="partners-remove">Remove</button>`;
}

// How well Scout's ranking agrees with the team's own history.
async function loadRecall(co) {
  const box = $("#recall-box");
  if (!box) return;
  try {
    const r = await api(`/api/companies/${co.id}/recall`);
    if (!r.partners) { box.innerHTML = ""; return; }
    box.innerHTML = r.found
      ? `<div class="recall"><b>Check against your history:</b> ${r.found} of your ${r.partners} past partners are in Scout's results;
          <b>${r.in_top_quarter}</b> of them rank in the top quarter${r.median_rank_pct != null ? ` (median: top ${r.median_rank_pct}%)` : ""}.
          <ul>${r.rows.slice(0, 5).map((x) => `<li>${esc(x.name)}: #${x.rank} of ${r.library} · fit ${x.fit ?? "—"}</li>`).join("")}</ul></div>`
      : `<div class="recall">None of your ${r.partners} past partners are in Scout's results yet. Run searches in their markets to check whether Scout finds them.</div>`;
  } catch { box.innerHTML = ""; }
}

async function uploadPartners(co, input) {
  const file = input.files[0];
  input.value = "";
  if (!file) return;
  const box = $("#partners-box");
  box.innerHTML = `<span class="loading-line"><span class="spinner"></span>Reading ${esc(file.name)}…</span>`;
  try {
    const r = await api(`/api/companies/${co.id}/partners?filename=${encodeURIComponent(file.name)}`, { method: "POST", body: file });
    co.partners = r.partners;
    box.innerHTML = partnersHtml(co.partners);
    toast(`${r.partners.count} past partners imported${r.in_library ? `, ${r.in_library} already in your results` : ""}`, "ok");
    S.companies = await api("/api/companies");
    S.company = S.companies.find((x) => x.id === co.id) || S.company;
    loadRecall(co);
    refresh();
  } catch (err) {
    box.innerHTML = partnersHtml(co.partners);
    toast(err.message, "err");
  }
}

async function removePartners(co) {
  if (!confirm("Remove the imported collaboration history?")) return;
  try {
    await api(`/api/companies/${co.id}/partners`, { method: "DELETE" });
    co.partners = null;
    $("#partners-box").innerHTML = partnersHtml(null);
    $("#recall-box").innerHTML = "";
    S.companies = await api("/api/companies");
    refresh();
  } catch (err) { toast(err.message, "err"); }
}

// ---------- Shortlist ----------
async function updateShortlistCount() {
  if (!S.company) return;
  const data = await api(`/api/companies/${S.company.id}/creators?status=shortlist&page_size=1`).catch(() => null);
  $("#shortlist-count").textContent = data ? data.total : 0;
}

async function renderShortlist() {
  const data = await api(`/api/companies/${S.company.id}/creators?status=shortlist&page_size=500&sort=match`);
  S.rows = data.items;
  $("#shortlist-count").textContent = data.total;
  $("#export-csv").hidden = !data.total;
  const el = $("#shortlist");
  if (!data.total) {
    el.innerHTML = `<div class="empty"><h2>Your shortlist is empty</h2><p>Press the star on any creator (or <kbd>s</kbd>). They'll show up here, ready for outreach.</p>
      <button class="btn primary" data-view="discover">Browse creators</button></div>`;
    return;
  }
  const statuses = [["shortlisted", "Shortlisted"], ["contacted", "Contacted"], ["replied", "Replied"], ["declined", "Declined"]];
  el.innerHTML = `<div class="table-wrap"><table class="list">
    <thead><tr><th>Creator</th><th class="num">Fit</th><th class="num">Quality</th><th class="num">Followers</th><th class="num">Views</th><th class="num">Est. price</th><th>Market</th><th>Email</th><th>Status</th></tr></thead>
    <tbody>${data.items.map((c) => `
      <tr data-id="${esc(c.id)}">
        <td class="c-who"><div class="who">${avatar(c.avatar, c.name)}
          <div class="who-text"><div class="who-name"><span class="plat plat-${c.platform}">${ICONS[c.platform]}</span><b>${esc(c.name)}</b>${badges(c)}</div>
          <div class="who-sum">${esc(c.summary)}</div></div></div></td>
        <td class="num">${scoreHtml(c.fit, c, "fit")}</td>
        <td class="num">${scoreHtml(c.quality, c, "quality")}</td>
        <td class="num">${fmtNum(c.followers)}</td>
        <td class="num">${fmtNum(c.median_views ?? c.avg_views)}</td>
        <td class="num">${euro(c.price)}</td>
        <td class="c-mkt">${esc(c.country || "—")}</td>
        <td>${c.email ? `<button class="btn small" data-act="copy" data-text="${esc(c.email)}">${ICONS.copy} ${esc(c.email)}</button>` : '<span class="muted">—</span>'}</td>
        <td><select data-status-for="${esc(c.id)}">${statuses.map(([v, l]) => `<option value="${v}" ${c.status === v ? "selected" : ""}>${l}</option>`).join("")}
          <option value="">Remove</option></select></td>
      </tr>`).join("")}</tbody></table></div>`;
}

// ---------- Views ----------
function showView(view) {
  S.view = view;
  closePanel();
  $$(".tab").forEach((t) => t.classList.toggle("on", t.dataset.view === view));
  $("#view-discover").hidden = view !== "discover";
  $("#view-shortlist").hidden = view !== "shortlist";
  renderBulk();
  if (view === "shortlist") renderShortlist();
  else loadCreators();
}

function refresh() {
  if (S.view === "shortlist") renderShortlist();
  else loadCreators();
  updateShortlistCount();
}

function setMode(mode) {
  S.mode = mode;
  try { localStorage.setItem("scout.mode", mode); } catch { /* storage blocked */ }
  $$("#view-mode button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  loadCreators();
}

// ---------- Events ----------
const typing = () => ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) || document.activeElement.isContentEditable;

function bindEvents() {
  const q = $("#q");
  q.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); runQuery(q.value); }
    else if (e.key === "Escape") { hideRecent(); q.blur(); }
  });
  q.addEventListener("focus", showRecent);
  q.addEventListener("input", () => {
    if (!q.value.trim()) {
      showRecent();
      if (S.f.q) { S.f.q = ""; $("#understood").hidden = true; filtersChanged({ debounce: true }); }
    } else hideRecent();
  });
  q.addEventListener("blur", () => setTimeout(hideRecent, 150));

  $("#f-sort").addEventListener("change", (e) => { S.f.sort = e.target.value; filtersChanged(); });
  $("#f-language").addEventListener("change", (e) => { S.f.language = e.target.value; filtersChanged(); });
  $("#f-min-score").addEventListener("input", (e) => { S.f.min_score = +e.target.value; $("#min-score-val").textContent = e.target.value; filtersChanged({ debounce: true }); });
  $("#f-min-eng").addEventListener("change", (e) => { S.f.min_eng = +e.target.value; filtersChanged(); });
  $("#f-has-email").addEventListener("change", (e) => { S.f.has_email = e.target.checked; filtersChanged(); });
  $("#f-growing").addEventListener("change", (e) => { S.f.growing = e.target.checked; filtersChanged(); });
  $("#f-gems").addEventListener("change", (e) => { S.f.gems = e.target.checked; filtersChanged(); });
  $("#f-hidden").addEventListener("change", (e) => { S.f.show_hidden = e.target.checked; filtersChanged(); });
  $("#c-scout").addEventListener("change", (e) => { S.f.ai_scout = e.target.checked; searchChanged({ reload: false }); });
  $("#size-lo").addEventListener("input", () => sizeFromSlider("lo"));
  $("#size-hi").addEventListener("input", () => sizeFromSlider("hi"));
  $("#company-btn").addEventListener("click", (e) => { e.stopPropagation(); toggleCompanyMenu(); });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.id === "tag-input" && e.target.value.trim()) {
      e.preventDefault();
      addTag(e.target.value.trim());
      $("#tag-add-btn").click();
      return;
    }
    if ($("dialog[open]")) return;
    if (e.key === "Escape") {
      if ($$(".pop:not([hidden]), .menu-pop").length) closePops();
      else if (S.panelId) closePanel();
      return;
    }
    if (typing() || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === "/") { e.preventDefault(); $("#q").focus(); return; }
    const c = S.rows[S.cursor];
    if (e.key === "ArrowDown" || e.key === "j") { e.preventDefault(); moveCursor(1); }
    else if (e.key === "ArrowUp" || e.key === "k") { e.preventDefault(); moveCursor(-1); }
    else if ((e.key === "Enter" || e.key === "o") && c) { e.preventDefault(); openPanel(c.id); }
    else if (e.key === "s" && c) toggleStar(c.id);
    else if (e.key === "x" && c && S.view === "discover") toggleSelect(c.id);
    else if (e.key === "h" && c && S.view === "discover") {
      openPanel(c.id).then(() => { const b = $('[data-act="panel-hide"]'); if (b) reasonMenu(b, (r) => hideCreator(c.id, r)); });
    }
  });

  // Images that fail to load become initials
  document.addEventListener("error", (e) => {
    const img = e.target;
    if (img.tagName !== "IMG") return;
    if (img.dataset.name != null) img.outerHTML = placeholder(img.dataset.name);
    else img.style.visibility = "hidden";
  }, true);

  document.addEventListener("change", async (e) => {
    if (e.target.id === "sel-all") {
      S.rows.forEach((c) => (e.target.checked ? S.selected.add(c.id) : S.selected.delete(c.id)));
      loadCreators({ quiet: true });
      renderBulk();
      return;
    }
    const box = e.target.closest("[data-select]");
    if (box) { toggleSelect(box.dataset.select, box.checked); return; }
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
    if (!e.target.closest(".pop, .pop-anchor, .menu-pop, [data-act='panel-hide'], [data-act='bulk-hide-menu']")) closePops();

    const companyBtn = e.target.closest("[data-company]");
    if (companyBtn) {
      const co = S.companies.find((c) => c.id === companyBtn.dataset.company);
      toggleCompanyMenu(false);
      if (co && co.id !== S.company.id) setCompany(co);
      return;
    }
    const popBtn = e.target.closest("#size-btn, #more-btn, #tag-add-btn");
    if (popBtn) {
      togglePop(popBtn);
      if (popBtn.id === "tag-add-btn" && !$("#tag-pop").hidden) { $("#tag-pop").innerHTML = tagPopHtml(); $("#tag-input").focus(); }
      return;
    }
    const recent = e.target.closest("[data-recent]");
    if (recent) { applyRecent(S.recent[+recent.dataset.recent]); return; }
    const viewBtn = e.target.closest("[data-view]");
    if (viewBtn) { showView(viewBtn.dataset.view); return; }
    const modeBtn = e.target.closest("[data-mode]");
    if (modeBtn) { setMode(modeBtn.dataset.mode); return; }
    const plat = e.target.closest("[data-platform]");
    if (plat) { S.f.platforms = plat.dataset.platform ? [plat.dataset.platform] : []; renderPlatforms(); searchChanged(); return; }
    const pageBtn = e.target.closest("[data-page]");
    if (pageBtn && !pageBtn.disabled) {
      S.page = +pageBtn.dataset.page;
      await loadCreators();
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    const sizePreset = e.target.closest("[data-size]");
    if (sizePreset) { const p = SIZE_PRESETS[+sizePreset.dataset.size]; setSize(p.min, p.max); return; }
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
    const star = e.target.closest("[data-star]");
    if (star) { toggleStar(star.dataset.star); return; }
    const row = e.target.closest("#grid [data-id], #shortlist [data-id]");
    if (row && !e.target.closest("[data-select], .c-sel, a, select, button")) {
      S.cursor = S.rows.findIndex((c) => c.id === row.dataset.id);
      markCursor();
      openPanel(row.dataset.id);
      return;
    }

    const actEl = e.target.closest("[data-act]");
    if (!actEl) return;
    const act = actEl.dataset.act;
    if (act === "close") { actEl.closest("dialog")?.close(); }
    else if (act === "go-discover") { e.preventDefault(); showView("discover"); }
    else if (act === "settings") { toggleCompanyMenu(false); openSettings(); }
    else if (act === "find") startFind();
    else if (act === "suggest-tags") suggestTags(actEl);
    else if (act === "undo-query" && S.undo) {
      S.f = S.undo;
      S.undo = null;
      $("#q").value = "";
      $("#understood").hidden = true;
      renderFilters();
      searchChanged();
    }
    else if (act === "reset-filters") {
      // Clear what narrows the list; keep the settings that only affect new searches.
      const keep = { deal_types: S.f.deal_types, avoid: S.f.avoid, example_creators: S.f.example_creators, ai_scout: S.f.ai_scout, sort: S.f.sort };
      S.f = { ...DEFAULT_FILTERS, ...keep };
      $("#q").value = "";
      $("#understood").hidden = true;
      closePops();
      renderFilters();
      searchChanged();
    }
    else if (act === "new-company") { toggleCompanyMenu(false); openCompanyForm(null); }
    else if (act === "edit-company") { toggleCompanyMenu(false); openCompanyForm(S.company); }
    else if (act === "dismiss-job") { S.job = null; renderJob(); }
    else if (act === "stop-job") {
      actEl.disabled = true;
      actEl.innerHTML = '<span class="spinner"></span> Stopping…';
      try { S.job = await api(`/api/jobs/${S.job.id}/stop`, { method: "POST" }); renderJob(); }
      catch (err) { toast(err.message, "err"); actEl.disabled = false; }
    }
    else if (act === "show-all") { S.viewJob = null; S.page = 1; loadCreators(); }
    else if (act === "retry-scoring") {
      actEl.disabled = true;
      try {
        S.job = await api(`/api/jobs/${S.job.id}/retry-scoring`, { method: "POST" });
        S.viewJob = S.job.id;
        renderJob();
        startPolling();
      } catch (err) { toast(err.message, "err"); actEl.disabled = false; }
    }
    else if (act === "bulk-shortlist") bulkStatus("shortlisted");
    else if (act === "bulk-hide-menu") reasonMenu(actEl, (r) => bulkStatus("hidden", r));
    else if (act === "bulk-clear") { S.selected.clear(); renderBulk(); loadCreators({ quiet: true }); }
    else if (act === "panel-close") closePanel();
    else if (act === "panel-prev") moveCursor(-1);
    else if (act === "panel-next") moveCursor(1);
    else if (act === "panel-star") toggleStar(S.panelId);
    else if (act === "panel-hide") { const id = S.panelId; reasonMenu(actEl, (r) => hideCreator(id, r)); }
    else if (act === "panel-unhide") { await setStatus(S.panelId, null); toast("Visible again"); openPanel(S.panelId); loadCreators({ quiet: true }); }
    else if (act === "deep") rescoreOne("deep", actEl);
    else if (act === "ai-check") rescoreOne("ai", actEl);
    else if (act === "pitch") draftPitch();
    else if (act === "copy") { await navigator.clipboard.writeText(actEl.dataset.text); toast("Copied"); }
    else if (act === "copy-pitch") { await navigator.clipboard.writeText($("#pitch-text").value); toast("Message copied"); }
    else if (act === "toggle-english" && S.pitch) {
      const showEnglish = actEl.dataset.shown === "orig";
      $("#pitch-text").value = showEnglish ? S.pitch.english : S.pitch.message;
      actEl.dataset.shown = showEnglish ? "en" : "orig";
      actEl.textContent = showEnglish ? "Show original" : "Show English";
    }
  });

  // Dialogs close on a backdrop click
  $$("dialog").forEach((d) => d.addEventListener("click", (e) => { if (e.target === d) d.close(); }));
}

// ---------- Boot ----------
(async function init() {
  bindEvents();
  try { S.mode = localStorage.getItem("scout.mode") || "table"; } catch { /* storage blocked */ }
  $$("#view-mode button").forEach((b) => b.classList.toggle("on", b.dataset.mode === S.mode));
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
