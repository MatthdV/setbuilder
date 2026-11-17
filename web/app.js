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
  suggReq: 0, galColor: "key",
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
const energyOf = (cid) => { const m = metaOf(cid); const e = m && (m.energy != null ? m.energy : m.energy_score); return e != null ? e : null; };
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
  sets.forEach((s) => { const o = document.createElement("option"); o.value = s.set_id; o.textContent = s.name + (s.set_type && s.set_type !== "custom" ? " · " + s.set_type : ""); sel.append(o); });
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
const GAL_K = 12;
// Nearest neighbours of `cid` on the 2D map (UMAP distance ~ sonic similarity).
function galaxyNeighbors(cid, k) {
  const me = state.galaxy.find((p) => p.content_id === cid);
  if (!me) return [];
  return state.galaxy.filter((p) => p !== me)
    .map((p) => [(p.umap_x - me.umap_x) ** 2 + (p.umap_y - me.umap_y) ** 2, p.content_id])
    .sort((a, b) => a[0] - b[0]).slice(0, k).map((x) => x[1]);
}

function renderGalaxy() {
  const setPath = state.set ? state.set.slots.filter((x) => x.content_id).map((x) => x.content_id) : [];
  const forced = state.set ? state.set.slots.filter((x) => x.is_forced).map((x) => x.content_id) : [];
  const sel = state.candidateId;
  drawGalaxy($("galaxy-canvas"), state.galaxy, state.byId, setPath, forced, {
    colorMode: state.galColor, energyOf,
    selectedId: sel, neighbors: sel ? new Set(galaxyNeighbors(sel, GAL_K)) : null,
  }, {
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

// Same mapping as the server (timeline.slot_position): count -> index, duration -> elapsed/target.
function slotPosFn(s) {
  const n = s.slots.length;
  if (s.mode === "duration" && s.target > 0) return (i) => Math.max(0, Math.min(1, (s.slots[i].start_time_s || 0) / s.target));
  return (i) => (n <= 1 ? 0 : i / (n - 1));
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
    drawCurve($("curve-svg"), s.curve_points, s.slots, energyOf, slotPosFn(s));
    drawTimeline($("timeline"), s.slots, state.selPos, selectSlot, titleOf, keyOf,
      (pos, cid) => placeTrack(pos, cid));
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
  $("btn-export2").disabled = !hasSet || !state.set.slots.some((x) => x.content_id);
  $("btn-delete").disabled = !hasSet;
  $("btn-rename").disabled = !hasSet;
  $("btn-place").disabled = !(hasSlot && hasCand);
  $("btn-force").disabled = !(hasSlot && hasCand);
  $("btn-clear-slot").disabled = !filledAtSel;
}

// ---- candidate selection (library row / galaxy click) ----
function setCandidate(cid) {
  state.candidateId = cid;
  renderGalaxy();
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

const CONFLICT = {
  duplicate_track: "Track already in this set.",
  slot_protected: "Slot is anchored/forced.",
};
async function placeTrack(pos, cid, isAnchor, overwrite) {
  try {
    await put(`/sets/${state.set.set_id}/slots/${pos}`, { content_id: cid, is_anchor: !!isAnchor, overwrite: !!overwrite });
    await openSet(state.set.set_id);
    state.selPos = pos; render(); renderSuggestionsPanel();
    toast("Track placed.");
    return true;
  } catch (e) {
    if (e.status === 409 && e.detail === "slot_protected" && !overwrite
        && confirm("This slot is anchored/forced. Overwrite it?")) return placeTrack(pos, cid, isAnchor, true);
    toast(e.status === 409 && CONFLICT[e.detail] || apiMessage(e, { 404: "Slot or track not found." }, "Could not place track."), true);
  }
}
// First empty slot at/after `from` (wrapping); -1 if the set is full.
function nextEmptySlot(from) {
  const sl = state.set ? state.set.slots : [];
  for (let k = 0; k < sl.length; k++) {
    const i = (from + k) % sl.length;
    if (!sl[i].content_id) return i;
  }
  return -1;
}

// Double-click on a library row: drop the track in the next empty slot, then
// select the following empty slot so the next double-click chains.
let quickBusy = false;  // serialize: a second double-click must not pick the same empty slot
async function quickPlace(t) {
  if (quickBusy) return;
  if (!state.set) { toast("Create or load a set first.", true); return; }
  const pos = nextEmptySlot(state.selPos != null ? state.selPos : 0);
  if (pos < 0) { toast("No empty slot left.", true); return; }
  quickBusy = true;
  try {
    if (await placeTrack(pos, t.content_id)) {
      const nxt = nextEmptySlot(pos + 1);
      if (nxt >= 0) await selectSlot(nxt);
    }
  } finally { quickBusy = false; }
}

// Player bar: jump back to the track being listened to, selected as candidate.
function locateTrack(cid) {
  setCandidate(cid);
  if (state.libView) state.libView.reveal(cid);
  $("lib-search").value = "";
}
// Player bar "Place": into the selected slot if any, else the next empty slot.
function placePlaying(cid) {
  if (!state.set) { toast("Create or load a set first.", true); return; }
  setCandidate(cid);
  if (state.selPos != null) placeTrack(state.selPos, cid);
  else quickPlace({ content_id: cid });
}

async function forceTrack(pos, cid, overwrite) {
  try {
    const res = await post(`/sets/${state.set.set_id}/slots/${pos}/force`, { content_id: cid, overwrite: !!overwrite });
    state.set = await get("/sets/" + state.set.set_id);
    state.selPos = pos; render(); renderSuggestionsPanel();
    renderImpact($("impact"), res.impact);
    toast("Track forced.");
  } catch (e) {
    if (e.status === 409 && e.detail === "slot_protected" && !overwrite
        && confirm("This slot is anchored/forced. Overwrite it?")) return forceTrack(pos, cid, true);
    toast(e.status === 409 && CONFLICT[e.detail] || apiMessage(e, { 404: "Track not found in library." }, "Could not force track."), true);
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

// ---- modal dialog (replaces confirm/prompt) ----
// askDialog({title, text, label, value, ok}) -> Promise<string|null>. With `label` it shows a text
// input (returns the trimmed value); without, it is a plain confirm (returns "" on OK).
function askDialog({ title, text, label, value, ok }) {
  return new Promise((resolve) => {
    const dlg = $("dlg"), input = $("dlg-input");
    $("dlg-title").textContent = title;
    $("dlg-text").textContent = text || "";
    $("dlg-label").textContent = label || "";
    $("dlg-label").hidden = input.hidden = !label;
    input.value = value || "";
    $("dlg-ok").textContent = ok || "OK";
    const done = () => {
      dlg.removeEventListener("close", done);
      resolve(dlg.returnValue === "ok" ? (label ? input.value.trim() : "") : null);
    };
    dlg.addEventListener("close", done);
    dlg.returnValue = "cancel";
    dlg.showModal();
    if (label) { input.focus(); input.select(); }
  });
}

// ---- export ----
async function exportSet() {
  if (!state.set) { toast("No set loaded.", true); return; }
  const name = await askDialog({
    title: "Export to Rekordbox",
    text: "Rekordbox must be closed (the export refuses to run otherwise). A backup of master.db is made automatically before anything is written.",
    label: "Playlist name", value: state.set.name, ok: "Export",
  });
  if (name === null) return;
  if (!name) { toast("Give the playlist a name.", true); return; }
  try {
    const r = await post(`/sets/${state.set.set_id}/export`, { name });
    toast(`Exported to Rekordbox: playlist "${r.playlist}" (${r.n_tracks} tracks). Backup: ${r.backup}`);
  } catch (e) {
    const msg = apiMessage(e, {
      400: "Empty set: nothing to export.",
      409: "Rekordbox is running — quit it completely, then export again.",
      422: "Invalid playlist name.",
      503: "Rekordbox extra missing (uv sync --extra rekordbox).",
    }, null);
    toast(msg || `Export failed (${e.status || "network"}${e.detail ? ": " + (typeof e.detail === "string" ? e.detail : "") : ""}).`, true);
  }
}

async function renameSet() {
  if (!state.set) return;
  const name = await askDialog({ title: "Rename set", label: "Set name", value: state.set.name, ok: "Rename" });
  if (!name) return;
  try {
    const rec = await _req("PATCH", `/sets/${state.set.set_id}`, { name });
    state.set.name = rec.name;
    await loadSets();
    toast("Set renamed.");
  } catch (e) {
    toast(apiMessage(e, { 422: "Invalid name." }, "Could not rename set."), true);
  }
}

// ---- create / delete set ----
async function createSet() {
  const mode = $("f-mode").value;
  const nSlots = parseInt($("f-slots").value, 10);
  // count mode: target == number of slots; duration mode: minutes -> seconds.
  const target = mode === "duration" ? parseFloat($("f-target").value) * 60 : nSlots;
  const body = {
    name: $("f-name").value || "Set",
    mode, target, n_slots: nSlots,
    set_type: $("f-type").value,
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
    onActivate: quickPlace,
    onCount: (shown, total) => {
      $("lib-count").textContent = shown === total ? `${total} tracks` : `${shown} / ${total}`;
    },
  });

  initPlayer(titleOf, () => {
    if (state.libView) state.libView.render();
    document.querySelectorAll(".sugg-card").forEach((c) => c.classList.toggle("playing", isPlaying(c.dataset.cid)));
    document.querySelectorAll(".btn-sm.pv").forEach((b) => { b.textContent = isPlaying(b.dataset.cid) ? "❚❚ Listen" : "▶ Listen"; });
  });
  const syncMode = () => { $("f-target-wrap").hidden = $("f-mode").value !== "duration"; };
  $("f-mode").addEventListener("change", syncMode); syncMode();
  $("gal-color").addEventListener("click", () => {
    state.galColor = state.galColor === "key" ? "energy" : "key";
    $("gal-color").textContent = "Color: " + state.galColor;
    $("gal-leg-key").hidden = state.galColor !== "key";
    $("gal-leg-en").hidden = state.galColor !== "energy";
    renderGalaxy();
  });
  $("btn-create").addEventListener("click", createSet);
  $("btn-delete").addEventListener("click", deleteSet);
  $("btn-rename").addEventListener("click", renameSet);
  $("f-existing").addEventListener("change", (ev) => { if (ev.target.value) openSet(ev.target.value); });
  const lv = $("lib-list"), topBtn = $("lib-top");
  lv.addEventListener("scroll", () => { topBtn.hidden = lv.scrollTop < 400; });
  topBtn.addEventListener("click", () => { lv.scrollTop = 0; });
  $("lib-search").addEventListener("input", (ev) => state.libView.setQuery(ev.target.value));
  $("btn-export").addEventListener("click", exportSet);
  $("btn-export2").addEventListener("click", exportSet);

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
