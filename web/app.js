// Orchestrateur de l'ecran unique. Consomme l'API du plan 4 ; aucune logique
// de scoring cote client. Etat minimal, re-render apres chaque mutation.
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

const state = { set: null, library: [], galaxy: [], selPos: null, titleById: {}, energyById: {} };

function toast(msg, isErr) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  setTimeout(() => t.classList.remove("show"), 4000);
}

const titleOf = (cid) => state.titleById[cid] || cid;

// ---- chargements ----
async function loadLibrary() {
  state.library = await get("/library");
  state.titleById = {};
  state.energyById = {};
  state.library.forEach((t) => {
    state.titleById[t.content_id] = (t.artist ? t.artist + " — " : "") + (t.title || t.content_id);
    if (t.energy_score != null) state.energyById[t.content_id] = t.energy_score;
  });
  renderLibrary(document.getElementById("lib-search").value);
}

async function loadGalaxy() { state.galaxy = await get("/galaxy"); }

async function loadSets() {
  const sets = await get("/sets");
  const sel = document.getElementById("f-existing");
  sel.textContent = "";
  const def = document.createElement("option"); def.value = ""; def.textContent = "— charger —"; sel.append(def);
  sets.forEach((s) => { const o = document.createElement("option"); o.value = s.set_id; o.textContent = s.name; sel.append(o); });
}

async function openSet(setId) {
  state.set = await get("/sets/" + setId);
  state.selPos = null;
  render();
}

// ---- rendu ----
function renderLibrary(filter) {
  const list = document.getElementById("lib-list");
  list.textContent = "";
  const q = (filter || "").toLowerCase();
  state.library
    .filter((t) => !q || [t.title, t.artist, t.genre].some((v) => (v || "").toLowerCase().includes(q)))
    .slice(0, 200)
    .forEach((t) => {
      const row = document.createElement("div");
      row.className = "lib-row";
      const name = document.createElement("span");
      name.textContent = (t.artist ? t.artist + " — " : "") + (t.title || t.content_id);
      const bpm = document.createElement("span"); bpm.className = "meta"; bpm.textContent = t.bpm ? Math.round(t.bpm) : "—";
      const key = document.createElement("span"); key.className = "meta"; key.textContent = t.camelot || "—";
      const en = document.createElement("span"); en.className = "meta"; en.textContent = t.energy_score != null ? t.energy_score.toFixed(1) : "—";
      row.append(name, bpm, key, en);
      row.addEventListener("click", () => { document.getElementById("force-cid").value = t.content_id; });
      list.append(row);
    });
}

function render() {
  if (!state.set) return;
  const s = state.set;
  drawCurve(document.getElementById("curve-svg"), s.curve_points, s.slots, state.energyById);
  drawTimeline(document.getElementById("timeline"), s.slots, state.selPos, selectSlot);
  const setPath = s.slots.filter((x) => x.content_id).map((x) => x.content_id);
  const forcedIds = s.slots.filter((x) => x.is_forced).map((x) => x.content_id);
  drawGalaxy(document.getElementById("galaxy-canvas"), state.galaxy, setPath, forcedIds, titleOf);
  document.getElementById("sel-pos").textContent = state.selPos == null ? "—" : state.selPos + 1;
}

async function selectSlot(pos) {
  state.selPos = pos;
  render();
  const breakdowns = await get(`/sets/${state.set.set_id}/slots/${pos}/suggestions?limit=15`);
  renderSuggestions(document.getElementById("sugg-list"), breakdowns, titleOf, (cid) => placeTrack(pos, cid));
  renderImpact(document.getElementById("impact"), null);
}

async function placeTrack(pos, cid, isAnchor) {
  await put(`/sets/${state.set.set_id}/slots/${pos}`, { content_id: cid, is_anchor: !!isAnchor });
  await openSet(state.set.set_id);
  state.selPos = pos; render();
}

async function forceTrack(pos, cid) {
  const res = await post(`/sets/${state.set.set_id}/slots/${pos}/force`, { content_id: cid });
  await get("/sets/" + state.set.set_id).then((s) => { state.set = s; });
  state.selPos = pos; render();
  renderImpact(document.getElementById("impact"), res.impact);
}

async function exportSet() {
  if (!state.set) { toast("Aucun set chargé.", true); return; }
  if (!confirm("Exporter vers Rekordbox ?\nRekordbox doit être FERMÉ. Un backup auto est fait avant écriture.")) return;
  try {
    const r = await post(`/sets/${state.set.set_id}/export`);
    toast(`Playlist « ${r.playlist} » : ${r.n_tracks} morceaux. Backup : ${r.backup}`);
  } catch (e) {
    const msg = { 400: "Set vide : rien à exporter.", 409: "Ferme Rekordbox et réessaie.",
                  503: "Extra Rekordbox absent (uv sync --extra rekordbox)." }[e.status] || (e.detail || "Échec export.");
    toast(msg, true);
  }
}

// ---- wiring ----
function wire() {
  document.getElementById("btn-create").addEventListener("click", async () => {
    const mode = document.getElementById("f-mode").value;
    const target = parseFloat(document.getElementById("f-target").value);
    const nSlots = parseInt(document.getElementById("f-slots").value, 10);
    const body = {
      name: document.getElementById("f-name").value || "Set",
      mode, target, n_slots: nSlots,
      curve_points: [[0, 2], [0.5, 9], [1, 4]],
    };
    try {
      const { set_id } = await post("/sets", body);
      await loadSets();
      document.getElementById("f-existing").value = set_id;
      await openSet(set_id);
      toast("Set créé.");
    } catch (e) { toast(e.detail || "Création impossible.", true); }
  });

  document.getElementById("f-existing").addEventListener("change", (ev) => { if (ev.target.value) openSet(ev.target.value); });
  document.getElementById("lib-search").addEventListener("input", (ev) => renderLibrary(ev.target.value));
  document.getElementById("btn-force").addEventListener("click", () => {
    if (state.selPos == null) { toast("Sélectionne un slot.", true); return; }
    const cid = document.getElementById("force-cid").value.trim();
    if (cid) forceTrack(state.selPos, cid);
  });
  document.getElementById("btn-export").addEventListener("click", exportSet);
}

async function boot() {
  wire();
  await Promise.all([loadLibrary(), loadGalaxy(), loadSets()]);
}
boot();
