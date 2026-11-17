// Orchestrator (single screen). Consumes the API; no scoring client-side.
// Minimal state, re-render after each mutation. English UI; server `detail`
// strings (French) are never shown — statuses map to English client messages.
const API = location.origin;

async function _req(method, path, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(API + path, opt);
  if (!r.ok) { const e = new Error(path); e.status = r.status; try { e.detail = (await r.json()).detail; } catch { /* no body */ } throw e; }
  return r.status === 204 ? null : r.json();
}
const get = (p) => _req("GET", p);
const post = (p, b) => _req("POST", p, b);
const put = (p, b) => _req("PUT", p, b);
const del = (p) => _req("DELETE", p);

// English client messages by status (we do NOT surface server `detail`).
function apiMessage(e, map, fallback) {
  return (map && map[e && e.status]) || fallback;
}

const state = {
  set: null, library: [], galaxy: [], byId: {},
  selPos: null, candidateId: null, analyzePoll: null, libView: null,
  suggReq: 0,
};

const $ = (id) => document.getElementById(id);

let toastTimer = null;
function toast(msg, isErr) {
  const t = $("toast");
  clearTimeout(toastTimer);
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  toastTimer = setTimeout(() => t.classList.remove("show"), 4000);
}

const metaOf = (cid) => state.byId[cid] || null;
const titleOf = (cid) => { const m = metaOf(cid); return m ? ((m.artist ? m.artist + " — " : "") + (m.title || cid)) : cid; };
const keyOf = (cid) => { const m = metaOf(cid); return m ? m.camelot : null; };
const energyOf = (cid) => { const m = metaOf(cid); return m && m.energy_score != null ? m.energy_score : null; };
const durOf = (cid) => { const m = metaOf(cid); return m && m.duration_s != null ? m.duration_s : null; };

function fmtLen(sec) {
  if (!sec || sec <= 0) return "—";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

// ---- loads ----
async function loadLibrary() {
  state.library = await get("/library");
  state.byId = {};
  state.library.forEach((t) => { state.byId[t.content_id] = t; });
  state.libView.setData(state.library);
}
async function loadGalaxy() { state.galaxy = await get("/galaxy"); }
async function loadSets() {
  const sets = await get("/sets");
  const sel = $("f-existing");
  sel.textContent = "";
  const def = document.createElement("option"); def.value = ""; def.textContent = "— load set —"; sel.append(def);
  sets.forEach((s) => { const o = document.createElement("option"); o.value = s.set_id; o.textContent = s.name; sel.append(o); });
  if (state.set) sel.value = state.set.set_id;
}
async function openSet(setId) {
  state.set = await get("/sets/" + setId);
  state.selPos = null;
  renderImpact($("impact"), null);
  render();
  renderSuggestionsPanel();
}

// ---- galaxy ----
function renderGalaxy() {
  const setPath = state.set ? state.set.slots.filter((x) => x.content_id).map((x) => x.content_id) : [];
  const forced = state.set ? state.set.slots.filter((x) => x.is_forced).map((x) => x.content_id) : [];
  drawGalaxy($("galaxy-canvas"), state.galaxy, state.byId, setPath, forced, {
    onHover: onGalaxyHover,
    onSelect: (cid) => setCandidate(cid),
  });
}

function onGalaxyHover(cid, ev) {
  const hc = $("hovercard");
  if (!cid || !ev) { hc.classList.remove("show"); return; }
  const m = metaOf(cid);
  hc.textContent = "";
  const t = document.createElement("div"); t.className = "hc-t"; t.textContent = m ? (m.title || cid) : cid;
  const s = document.createElement("div"); s.className = "hc-s"; s.textContent = m ? [m.artist, m.genre || m.top_genre].filter(Boolean).join(" · ") : "";
  const row = document.createElement("div"); row.className = "hc-row";
  row.append(keyChip(keyOf(cid)));
  const bpm = document.createElement("span"); bpm.className = "num"; bpm.textContent = (m && m.bpm != null) ? Math.round(m.bpm) : "—";
  row.append(bpm, energyBar(energyOf(cid)));
  hc.append(t, s, row);
  hc.style.left = Math.min(ev.clientX + 14, window.innerWidth - 220) + "px";
  hc.style.top = Math.min(ev.clientY + 14, window.innerHeight - 90) + "px";
  hc.classList.add("show");
}

// ---- render ----
function render() {
  const s = state.set;
  // readouts
  if (s) {
    const filled = s.slots.filter((x) => x.content_id);
    const len = filled.reduce((a, x) => a + (durOf(x.content_id) || 0), 0);
    const peaks = filled.map((x) => energyOf(x.content_id)).filter((e) => e != null);
    $("r-slots").textContent = s.slots.length;
    $("r-length").textContent = fmtLen(len);
    $("r-peak").textContent = peaks.length ? Math.max(...peaks).toFixed(1) : "—";
    $("slots-fig").textContent = `${filled.length}/${s.slots.length} FILLED`;
  } else {
    $("r-slots").textContent = $("r-length").textContent = $("r-peak").textContent = "—";
    $("slots-fig").textContent = "—";
  }

  if (s) {
    drawCurve($("curve-svg"), s.curve_points, s.slots, energyOf);
    drawTimeline($("timeline"), s.slots, state.selPos, selectSlot, titleOf, keyOf);
  } else {
    $("curve-svg").innerHTML = "";
    $("curve-alert").classList.remove("show");
    $("timeline").textContent = "";
  }
  renderGalaxy();

  $("sel-pos").textContent = state.selPos == null ? "—" : state.selPos + 1;
  updateButtons();
}

function updateButtons() {
  const hasSet = !!state.set;
  const hasSlot = hasSet && state.selPos != null;
  const hasCand = !!state.candidateId;
  const filledAtSel = hasSlot && !!state.set.slots[state.selPos].content_id;
  $("btn-export").disabled = !hasSet;
  $("btn-delete").disabled = !hasSet;
  $("btn-place").disabled = !(hasSlot && hasCand);
  $("btn-force").disabled = !(hasSlot && hasCand);
  $("btn-clear-slot").disabled = !filledAtSel;
}

// ---- candidate selection (library row / galaxy click) ----
function setCandidate(cid) {
  state.candidateId = cid;
  if (state.libView) state.libView.setSelected(cid);
  const strip = $("sel-strip");
  if (cid) {
    $("sel-name").textContent = titleOf(cid);
    strip.classList.remove("hidden");
  } else {
    strip.classList.add("hidden");
  }
  updateButtons();
}
function clearCandidate() { setCandidate(null); if (state.libView) state.libView.setSelected(null); }

// ---- slot / suggestions ----
async function selectSlot(pos) {
  state.selPos = pos;
  renderImpact($("impact"), null);  // l'impact appartient au dernier force, pas à la sélection
  render();
  renderSuggestionsPanel();
}
async function renderSuggestionsPanel() {
  const listEl = $("sugg-list");
  if (!state.set || state.selPos == null) {
    listEl.textContent = "";
    const p = document.createElement("div"); p.className = "empty-note";
    p.textContent = state.set ? "Select a slot to see suggestions." : "Create or load a set to start.";
    listEl.append(p);
    return;
  }
  listEl.textContent = "";
  listEl.append(Object.assign(document.createElement("div"), { className: "loading", textContent: "loading suggestions" }));
  // Guard against out-of-order responses: capture the request's set+slot and a
  // token; ignore the response if the selection has changed since.
  const reqSet = state.set.set_id, reqPos = state.selPos, reqId = ++state.suggReq;
  try {
    const breakdowns = await get(`/sets/${reqSet}/slots/${reqPos}/suggestions?limit=15`);
    if (reqId !== state.suggReq) return;
    renderSuggestions(listEl, breakdowns, titleOf, keyOf, (cid) => placeTrack(reqPos, cid));
  } catch (e) {
    if (reqId !== state.suggReq) return;
    listEl.textContent = "";
    const p = document.createElement("div"); p.className = "empty-note";
    p.textContent = "Could not load suggestions.";
    listEl.append(p);
  }
}

async function placeTrack(pos, cid, isAnchor) {
  try {
    await put(`/sets/${state.set.set_id}/slots/${pos}`, { content_id: cid, is_anchor: !!isAnchor });
    await openSet(state.set.set_id);
    state.selPos = pos; render(); renderSuggestionsPanel();
    toast("Track placed.");
  } catch (e) {
    toast(apiMessage(e, { 404: "Slot or track not found." }, "Could not place track."), true);
  }
}
async function forceTrack(pos, cid) {
  try {
    const res = await post(`/sets/${state.set.set_id}/slots/${pos}/force`, { content_id: cid });
    state.set = await get("/sets/" + state.set.set_id);
    state.selPos = pos; render(); renderSuggestionsPanel();
    renderImpact($("impact"), res.impact);
    toast("Track forced.");
  } catch (e) {
    toast(apiMessage(e, { 404: "Track not found in library." }, "Could not force track."), true);
  }
}
async function clearSlot(pos) {
  try {
    await del(`/sets/${state.set.set_id}/slots/${pos}`);
    await openSet(state.set.set_id);
    state.selPos = pos; render(); renderSuggestionsPanel();
    toast("Slot cleared.");
  } catch (e) {
    toast(apiMessage(e, { 404: "Slot not found." }, "Could not clear slot."), true);
  }
}

// ---- analyze ----
async function refreshAnalyze() {
  const el = $("analyze-panel");
  try {
    const [pend, status] = await Promise.all([get("/analyze/pending"), get("/analyze/status")]);
    renderAnalyze(el, pend, status, startAnalyze);
    if (status.state === "running" && !state.analyzePoll) {
      state.analyzePoll = setInterval(pollAnalyze, 2000);
    }
    return status;
  } catch (e) {
    el.textContent = "";
    el.append(Object.assign(document.createElement("div"), { className: "an-banner err", textContent: "Analysis status unavailable." }));
  }
}
async function pollAnalyze() {
  let status;
  try { status = await get("/analyze/status"); } catch { return; }
  if (["done", "error", "idle", "stale"].includes(status.state)) {
    clearInterval(state.analyzePoll);
    state.analyzePoll = null;
    // analysis populates energy + galaxy -> reload BOTH, then re-render
    await Promise.all([loadLibrary().catch(() => {}), loadGalaxy().catch(() => {})]);
    await refreshAnalyze();
    render();
    if (state.set) renderSuggestionsPanel();
    return;
  }
  renderAnalyze($("analyze-panel"), await get("/analyze/pending").catch(() => ({})), status, startAnalyze);
}
async function startAnalyze() {
  try {
    await post("/analyze");
    toast("Analysis started.");
    await refreshAnalyze();
    if (!state.analyzePoll) state.analyzePoll = setInterval(pollAnalyze, 2000);
  } catch (e) {
    toast(apiMessage(e, { 409: "Analysis already running or Rekordbox is open." }, "Could not start analysis."), true);
    await refreshAnalyze();
  }
}

// ---- export ----
async function exportSet() {
  if (!state.set) { toast("No set loaded.", true); return; }
  if (!confirm("Export to Rekordbox?\nRekordbox must be CLOSED. An automatic backup is made before writing.")) return;
  try {
    const r = await post(`/sets/${state.set.set_id}/export`);
    toast(`Playlist "${r.playlist}": ${r.n_tracks} tracks. Backup: ${r.backup}`);
  } catch (e) {
    toast(apiMessage(e, {
      400: "Empty set: nothing to export.",
      409: "Close Rekordbox and try again.",
      503: "Rekordbox extra missing (uv sync --extra rekordbox).",
    }, "Export failed."), true);
  }
}

// ---- create / delete set ----
async function createSet() {
  const mode = $("f-mode").value;
  const target = parseFloat($("f-target").value);
  const nSlots = parseInt($("f-slots").value, 10);
  const body = {
    name: $("f-name").value || "Set",
    mode, target, n_slots: nSlots,
    curve_points: [[0, 2], [0.5, 9], [1, 4]],
  };
  try {
    const { set_id } = await post("/sets", body);
    await loadSets();
    $("f-existing").value = set_id;
    await openSet(set_id);
    toast("Set created.");
  } catch (e) {
    toast(apiMessage(e, { 422: "Invalid set parameters." }, "Could not create set."), true);
  }
}
async function deleteSet() {
  if (!state.set) return;
  if (!confirm(`Delete set "${state.set.name}"? This cannot be undone.`)) return;
  const id = state.set.set_id;
  try {
    await del("/sets/" + id);
    state.set = null; state.selPos = null; clearCandidate();
    await loadSets();
    render(); renderSuggestionsPanel();
    toast("Set deleted.");
  } catch (e) {
    toast(apiMessage(e, {}, "Could not delete set."), true);
  }
}

// ---- wiring ----
function wire() {
  state.libView = createLibraryView($("lib-list"), {
    onSelect: (t) => setCandidate(t.content_id),
    onCount: (shown, total) => {
      $("lib-count").textContent = shown === total ? `${total} tracks` : `${shown} / ${total}`;
    },
  });

  $("btn-create").addEventListener("click", createSet);
  $("btn-delete").addEventListener("click", deleteSet);
  $("f-existing").addEventListener("change", (ev) => { if (ev.target.value) openSet(ev.target.value); });
  $("lib-search").addEventListener("input", (ev) => state.libView.setQuery(ev.target.value));
  $("btn-export").addEventListener("click", exportSet);

  // sortable headers
  document.querySelectorAll(".lhead span[data-sort]").forEach((h) => {
    h.addEventListener("click", () => {
      const { key, dir } = state.libView.setSort(h.dataset.sort);
      document.querySelectorAll(".lhead span").forEach((x) => x.classList.remove("sorted", "desc"));
      h.classList.add("sorted"); if (dir < 0) h.classList.add("desc");
    });
  });

  // candidate place / force / clear
  $("btn-place").addEventListener("click", () => {
    if (state.selPos == null) { toast("Select a slot.", true); return; }
    if (!state.candidateId) { toast("Select a track.", true); return; }
    placeTrack(state.selPos, state.candidateId);
  });
  $("btn-force").addEventListener("click", () => {
    if (state.selPos == null) { toast("Select a slot.", true); return; }
    if (!state.candidateId) { toast("Select a track.", true); return; }
    forceTrack(state.selPos, state.candidateId);
  });
  $("btn-clear-slot").addEventListener("click", () => {
    if (state.selPos == null) { toast("Select a slot.", true); return; }
    clearSlot(state.selPos);
  });
  $("sel-clear").addEventListener("click", clearCandidate);

  // redraw galaxy on resize (DPR/backing-store)
  let rz = false;
  window.addEventListener("resize", () => {
    if (rz) return; rz = true;
    requestAnimationFrame(() => { rz = false; renderGalaxy(); });
  });
}

async function boot() {
  wire();
  // library + galaxy first so the screen is useful without a set
  try {
    await Promise.all([loadLibrary(), loadGalaxy()]);
  } catch (e) {
    toast("Could not load library or galaxy.", true);
  }
  render();
  renderSuggestionsPanel();
  await Promise.all([loadSets().catch(() => {}), refreshAnalyze()]);
}
boot();
