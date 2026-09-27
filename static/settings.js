"use strict";

// Settings dialog: which AI to use, API keys, the local model. Uses the helpers in app.js.
const DATA_KEY_LINKS = {
  youtube: "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
  twitch: "https://dev.twitch.tv/console/apps",
};

async function openSettings() {
  let st;
  try { st = await api("/api/settings"); } catch (e) { return toast(e.message, "err"); }
  const dlg = $("#settings");
  let provider = st.ai_provider;
  let writer = st.writer_provider || "";
  const drafts = {}; // unsaved edits per provider, so switching back and forth keeps what was typed
  let local = null;  // /api/local-ai: this computer, the recommended model, Ollama status, download
  const removeWebhook = {}; // channel -> true once "Remove" was clicked (applied on Save)
  let localTimer = null;

  dlg.innerHTML = `
    <form id="settings-form" autocomplete="off">
      <div class="dlg-head">
        <div><h2 id="settings-title">Settings</h2><p>Keys are saved only on this computer and are never shown again in full.</p></div>
        <button type="button" class="x" data-act="close" aria-label="Close">${ICONS.x}</button>
      </div>
      <div class="dlg-body">
        <section class="set-section">
          <h3>Search AI</h3>
          <p class="muted small">Plans searches and checks creators, many times per search. <b>Local AI</b> runs on this computer for free.</p>
          <div class="provider-grid" id="ai-providers"></div>
          <div id="ai-fields" class="ai-fields"></div>
        </section>
        <section class="set-section">
          <h3>Writing AI</h3>
          <p class="muted small">Only used when you click <i>Draft a message</i> or <i>Deep evaluation</i>. A paid AI writes better Finnish or German, and costs cents per message.</p>
          <select id="writer-provider" class="model-select" aria-label="Writing AI"></select>
        </section>
        <section class="set-section">
          <h3>Data sources</h3>
          ${dataKeyField("youtube", "YouTube API key", st.youtube_key_hint, "Free: Google Cloud console → enable YouTube Data API v3 → Credentials → Create API key.")}
          <p class="note">TikTok needs no key: Scout reads TikTok's public pages itself.</p>
          <div class="field"><span>Twitch <em class="opt">optional</em></span>
            <div class="key-row">
              <input type="text" id="twitch-id" autocomplete="off" placeholder="${st.twitch_id_hint ? `Client ID saved (${esc(st.twitch_id_hint)})` : "Client ID"}">
              <input type="password" id="twitch-secret" autocomplete="new-password" placeholder="${st.twitch_secret_hint ? `Secret saved (${esc(st.twitch_secret_hint)})` : "Client Secret"}">
              <a class="btn small" href="${DATA_KEY_LINKS.twitch}" target="_blank" rel="noopener">${ICONS.ext} Get them</a>
              <button type="button" class="btn small" data-act="test-twitch">Test</button>
            </div>
            <span class="test-msg" id="twitch-msg"></span>
            <small>Free: dev.twitch.tv → Your Console → Register Your Application (any name, OAuth redirect http://localhost, category Other) → copy the Client ID and create a Client Secret. Adds Twitch to searches, with its language filter for small markets.</small>
          </div>
        </section>
        <section class="set-section">
          <h3>Notifications <em class="opt">optional</em></h3>
          <p class="muted small">When a repeating search finds new creators, Scout posts the best ones (and any rising star) to your team's chat. Add Slack, Teams or both.</p>
          ${webhookField("slack", "Slack", st.slack_webhook_hint, "https://hooks.slack.com/services/…",
            "In Slack: api.slack.com/apps → Create New App → Incoming Webhooks → turn on → Add New Webhook → pick the channel → copy the Webhook URL.")}
          ${webhookField("teams", "Microsoft Teams", st.teams_webhook_hint, "https://…/workflows/…",
            "In Teams: open the channel → ⋯ → Workflows → “Post to a channel when a webhook request is received” → Next → Add workflow → copy the URL.")}
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
      base_url: $("#ai-url")?.value.trim() ?? drafts[provider]?.base_url ?? null,
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

  const renderWriter = () => {
    const opts = Object.entries(st.providers).filter(([k, p]) => !p.local && (p.key_hint || k === writer));
    $("#writer-provider").innerHTML = `<option value="">Same as the search AI (${esc(st.providers[provider].label)})</option>`
      + opts.map(([k, p]) => `<option value="${k}" ${k === writer ? "selected" : ""}>${esc(p.label)}${p.model ? ` (${esc(p.model)})` : ""}</option>`).join("")
      + (opts.length ? "" : `<option disabled>Add an OpenAI, Gemini or OpenRouter key above to use it here</option>`);
  };

  const gb = (bytes) => (bytes / 1024 ** 3).toFixed(1);
  const localHtml = () => {
    if (!local) return `<div class="loading-line"><span class="spinner"></span>Looking at this computer…</div>`;
    const { hardware: hw, recommended: rec, ollama, pull } = local;
    const gpu = hw.dedicated_gpu ? `${esc(hw.dedicated_gpu.name)}${hw.dedicated_gpu.vram_gb ? ` (${hw.dedicated_gpu.vram_gb} GB)` : ""}`
      : `${hw.gpus[0] ? esc(hw.gpus[0].name) + ", " : ""}no dedicated graphics card`;
    const have = ollama.models.map((m) => m.name);
    const d = drafts[provider] || {};
    const current = d.model ?? st.providers.ollama.model;
    const pulling = pull && !pull.done;
    let status = "";
    if (!ollama.installed) {
      status = `<p class="note">Local AI needs <b>Ollama</b> (free). Install it, then reopen Settings.
        <a class="btn small" href="https://ollama.com/download" target="_blank" rel="noopener">${ICONS.ext} Get Ollama</a></p>`;
    } else if (!ollama.running) {
      status = `<p class="note">Ollama is installed but not running. <button type="button" class="btn small" data-act="start-ollama">Start it</button></p>`;
    }
    const recBox = `<div class="rec">
        <div><b>Recommended for this computer: ${esc(rec.model)}</b> <span class="muted">· ${rec.size_gb} GB</span>
          <small>${esc(rec.note)}. Why: ${esc(rec.why)}.</small></div>
        ${have.includes(rec.model) ? `<span class="pill partner">✓ Downloaded</span>`
          : pulling ? "" : `<button type="button" class="btn small primary" data-act="pull" data-model="${esc(rec.model)}" ${ollama.running && rec.fits_disk ? "" : "disabled"}>Download</button>`}
      </div>
      ${rec.fits_disk ? "" : `<p class="note bad">Not enough free disk space (${hw.free_disk_gb} GB free).</p>`}`;
    const progress = pull ? (pull.error ? `<p class="test-msg bad">✗ ${esc(pull.error)}</p>`
      : pull.done ? "" : `<div class="pull"><div class="bar"><i style="width:${pull.total ? Math.round(pull.completed / pull.total * 100) : 2}%"></i></div>
        <small>Downloading ${esc(pull.model)}: ${pull.total ? `${gb(pull.completed)} of ${gb(pull.total)} GB` : esc(pull.status || "starting")}. You can keep using Scout.</small></div>`) : "";
    const others = local.catalog.filter((m) => m.model !== rec.model).map((m) => `
      <li><span><b>${esc(m.model)}</b> · ${m.size_gb} GB · ${esc(m.note)}</span>
        ${have.includes(m.model) ? '<span class="muted">downloaded</span>' : `<button type="button" class="btn small" data-act="pull" data-model="${esc(m.model)}" ${ollama.running && !pulling ? "" : "disabled"}>Download</button>`}</li>`).join("");
    return `
      <p class="hw">This computer: <b>${hw.ram_gb ?? "?"} GB</b> memory · ${gpu} · ${hw.cpu_threads} processor threads</p>
      ${status}${recBox}${progress}
      ${have.length ? `<div class="field"><span>Model to use</span>
        <select id="ai-model" class="model-select">${have.map((m) => `<option value="${esc(m)}" ${m === current ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></div>` : ""}
      <details class="other-models"><summary>Other sizes</summary><ul>${others}</ul></details>`;
  };

  const refreshLocal = async () => {
    clearTimeout(localTimer);
    if (provider === "ollama") readFields(); // keep a model the user just picked
    try { local = await api("/api/local-ai"); } catch (err) { toast(err.message, "err"); return; }
    const have = local.ollama.models.map((m) => m.name);
    const d = drafts.ollama || {};
    const current = d.model || st.providers.ollama.model;
    // A fresh download (or a saved model that isn't there any more) -> the recommended one if we have it.
    if (!have.includes(current) && have.length) {
      drafts.ollama = { ...d, model: have.includes(local.recommended.model) ? local.recommended.model : have[0] };
    }
    if (provider === "ollama" && $("#local-ai")) $("#local-ai").innerHTML = localHtml();
    if (local.pull && !local.pull.done && dlg.open) localTimer = setTimeout(refreshLocal, 1500);
    else if (local.pull?.done && !local.pull.error && local.pull.model && !local._announced) {
      local._announced = true;
      toast(`${local.pull.model} is ready`, "ok");
    }
  };

  const renderFields = () => {
    const p = st.providers[provider];
    renderWriter();
    if (p.local) {
      $("#ai-fields").innerHTML = `<div id="local-ai" class="local-ai">${localHtml()}</div>
        <div class="test-row">
          <button type="button" class="btn small" data-act="test-ai">Test ${esc(p.label)}</button>
          <span class="test-msg" id="ai-test-msg"></span>
        </div>`;
      if (!local) refreshLocal();
      return;
    }
    const d = drafts[provider] || {};
    let model = d.model ?? p.model;
    const l = loaded[provider];
    if (l && !l.manual && !l.models.includes(model)) model = l.recommended;
    const keyField = p.needs_key || (p.editable_url && !p.local) ? `
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
      ${p.editable_url ? `<div class="field"><span>Address</span>
        <input type="url" id="ai-url" value="${esc(d.base_url ?? p.base_url)}" placeholder="${provider === "gpu" ? "http://YOUR-SERVER-IP:8000/v1" : "https://your-server/v1"}">
        ${provider === "gpu" ? `<small>Run <code>scripts/verda_setup.sh</code> on the server once; it prints the address and key to paste here.</small>` : ""}</div>` : ""}
      <div class="field"><span>Model</span>
        <div class="key-row">
          ${modelFieldHtml(p, model)}
          <button type="button" class="btn small" data-act="load-models">${l ? "Reload" : "Load models"}</button>
        </div>
      </div>
      <div class="test-row">
        <button type="button" class="btn small" data-act="test-ai">Test ${esc(p.label)}</button>
        <span class="test-msg" id="ai-test-msg"></span>
      </div>`;
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
    if (e.target.id === "writer-provider") { writer = e.target.value; return; }
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
    return { target: "ai", provider, api_key: d.api_key || null, model: d.model || null, base_url: d.base_url || null };
  };

  const showResult = (el, r) => {
    el.className = `test-msg ${r.ok ? "ok" : "bad"}`;
    el.textContent = (r.ok ? "✓ " : "✗ ") + r.message;
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
    if (act === "pull") {
      btn.disabled = true;
      try {
        await api("/api/local-ai/pull", { method: "POST", body: { model: btn.dataset.model } });
        await refreshLocal();
      } catch (err) { toast(err.message, "err"); btn.disabled = false; }
    } else if (act === "start-ollama") {
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> Starting…';
      try { await api("/api/local-ai/start", { method: "POST" }); await refreshLocal(); }
      catch (err) { toast(err.message, "err"); btn.disabled = false; btn.textContent = "Start it"; }
    } else if (act === "clear-ai-key") {
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
    } else if (act === "test-webhook") {  // the address typed in the field, else the saved one
      const channel = btn.dataset.channel;
      btn.disabled = true;
      const msg = $(`#${channel}-webhook-msg`);
      msg.className = "test-msg"; msg.textContent = "Sending…";
      const body = { target: channel, webhook_url: $(`#${channel}-webhook`).value.trim() || null };
      try { showResult(msg, await api("/api/settings/test", { method: "POST", body })); }
      catch (err) { showResult(msg, { ok: false, message: err.message }); }
      finally { btn.disabled = false; }
    } else if (act === "clear-webhook") {
      const channel = btn.dataset.channel;
      removeWebhook[channel] = true;
      const input = $(`#${channel}-webhook`);
      input.value = "";
      input.placeholder = "Removed when you save. Paste a new one to keep posting";
      btn.remove();
    } else if (act === "test-youtube" || act === "test-twitch") {
      const which = act.slice(5);
      btn.disabled = true;
      const msg = $(`#${which}-msg`);
      msg.className = "test-msg"; msg.textContent = "Testing…";
      const body = { target: which, youtube_api_key: $("#youtube-key").value.trim() || null,
        twitch_client_id: $("#twitch-id").value.trim() || null, twitch_client_secret: $("#twitch-secret").value.trim() || null };
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
      writer_provider: writer,
      providers: Object.fromEntries(Object.entries(drafts).map(([k, d]) => [k, {
        api_key: d.api_key || null, model: d.model ?? null, base_url: d.base_url ?? null, clear_key: !!d.clear_key,
      }])),
      youtube_api_key: $("#youtube-key").value.trim() || null,
      twitch_client_id: $("#twitch-id").value.trim() || null,
      twitch_client_secret: $("#twitch-secret").value.trim() || null,
      ...Object.fromEntries(["slack", "teams"].flatMap((channel) => {
        const url = $(`#${channel}-webhook`).value.trim();
        return [[`${channel}_webhook`, url || null], [`clear_${channel}_webhook`, !url && !!removeWebhook[channel]]];
      })),
    };
    try {
      await api("/api/settings", { method: "PUT", body });
      S.meta = await api("/api/meta");
      renderFilters();
      dlg.close();
      toast(S.meta.ai.ready ? `Saved. Searches use ${S.meta.ai.label} (${S.meta.ai.model}); messages use ${S.meta.ai.writer.label}.` : "Saved", "ok");
    } catch (err) { toast(err.message, "err"); }
  };

  dlg.addEventListener("close", () => clearTimeout(localTimer), { once: true });
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

// A team-chat webhook (Slack or Teams): paste, test, remove.
function webhookField(channel, label, hint, placeholder, help) {
  return `
    <div class="field"><span>${esc(label)}</span>
      <div class="key-row">
        <input type="password" id="${channel}-webhook" autocomplete="off" spellcheck="false" aria-label="${esc(label)} webhook address"
          placeholder="${hint ? `Saved (${esc(hint)}). Paste a new one to replace it` : esc(placeholder)}">
        <button type="button" class="btn small" data-act="test-webhook" data-channel="${channel}">Send a test</button>
      </div>
      ${hint ? `<button type="button" class="btn link small-link" data-act="clear-webhook" data-channel="${channel}">Remove saved webhook</button>` : ""}
      <span class="test-msg" id="${channel}-webhook-msg"></span>
      <small>${esc(help)}</small>
    </div>`;
}
