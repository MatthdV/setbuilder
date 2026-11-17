// Virtualized library view over the FULL library (~4000 tracks). Fixed-height
// rows + scroll container + top/bottom spacers + a filtered/sorted index. Only
// the visible window (+overscan) is in the DOM. DOM-built, no innerHTML.
//
// createLibraryView(container, { onSelect, onCount }) -> controller.
//   container: the scroll viewport element.
//   onSelect(track): row clicked.
//   onCount(shown, total): filtered count changed.
function createLibraryView(container, opts) {
  opts = opts || {};
  const onSelect = opts.onSelect || function () {};
  const onCount = opts.onCount || function () {};
  const ROW_H = 38, OVERSCAN = 8;

  let all = [], view = [], query = "", sortKey = null, sortDir = 1, selectedId = null;

  container.classList.add("lib-viewport");
  container.textContent = "";
  const inner = document.createElement("div");
  inner.className = "lib-inner";
  const topSpacer = document.createElement("div");
  const rowsEl = document.createElement("div");
  const bottomSpacer = document.createElement("div");
  inner.append(topSpacer, rowsEl, bottomSpacer);
  container.append(inner);

  function sCmp(a, b) {
    a = (a || "").toLowerCase(); b = (b || "").toLowerCase();
    if (!a && b) return 1; if (a && !b) return -1;
    return a < b ? -1 : a > b ? 1 : 0;
  }
  function nCmp(a, b) {
    const an = a == null, bn = b == null;
    if (an && bn) return 0; if (an) return 1; if (bn) return -1;
    return a - b;
  }
  const CMP = {
    title: (a, b) => sCmp(a.title, b.title),
    artist: (a, b) => sCmp(a.artist, b.artist),
    genre: (a, b) => sCmp(a.genre || a.top_genre, b.genre || b.top_genre),
    key: (a, b) => sCmp(a.camelot, b.camelot),
    bpm: (a, b) => nCmp(a.bpm, b.bpm),
    energy: (a, b) => nCmp(a.energy_score, b.energy_score),
  };

  function buildIndex() {
    all.forEach((t) => {
      t._search = [t.title, t.artist, t.genre, t.top_genre, t.camelot,
        t.bpm != null ? Math.round(t.bpm) : ""].join(" ").toLowerCase();
    });
  }

  function recompute() {
    view = query ? all.filter((t) => t._search.includes(query)) : all.slice();
    if (sortKey && CMP[sortKey]) {
      // Valeurs manquantes toujours en bas, quel que soit le sens du tri.
      const miss = (t) => {
        const v = sortKey === "genre" ? (t.genre || t.top_genre)
          : sortKey === "key" ? t.camelot : sortKey === "energy" ? t.energy_score : t[sortKey];
        return v == null || v === "";
      };
      view.sort((a, b) => {
        const ma = miss(a), mb = miss(b);
        if (ma !== mb) return ma ? 1 : -1;
        return CMP[sortKey](a, b) * sortDir;
      });
    }
    container.scrollTop = 0;
    render();
    onCount(view.length, all.length);
  }

  function render() {
    const total = view.length;
    const vh = container.clientHeight || 320;
    let start = Math.max(0, Math.floor(container.scrollTop / ROW_H) - OVERSCAN);
    const count = Math.ceil(vh / ROW_H) + 2 * OVERSCAN;
    let end = Math.min(total, start + count);
    topSpacer.style.height = (start * ROW_H) + "px";
    bottomSpacer.style.height = Math.max(0, (total - end) * ROW_H) + "px";
    rowsEl.textContent = "";
    if (total === 0) {
      const e = document.createElement("div");
      e.className = "empty-note";
      e.textContent = "No tracks match.";
      rowsEl.append(e);
      return;
    }
    for (let i = start; i < end; i++) rowsEl.append(buildRow(view[i], i));
  }

  function buildRow(t, i) {
    const r = document.createElement("div");
    r.className = "lrow" + (t.content_id === selectedId ? " sel" : "");
    const idx = document.createElement("span");
    idx.className = "idx";
    const pb = document.createElement("button");
    pb.className = "pv" + (typeof isPlaying === "function" && isPlaying(t.content_id) ? " on" : "");
    pb.textContent = (typeof isPlaying === "function" && isPlaying(t.content_id)) ? "❚❚" : "▶";
    pb.title = "Preview";
    pb.addEventListener("click", (ev) => { ev.stopPropagation(); previewToggle(t.content_id); });
    idx.append(pb);
    const nm = document.createElement("span"); nm.className = "nm";
    const b = document.createElement("b"); b.textContent = t.title || t.content_id;
    const s = document.createElement("s"); s.textContent = t.artist || "";
    nm.append(b, s);
    const bpm = document.createElement("span");
    bpm.className = "r bpm"; bpm.textContent = t.bpm != null ? Math.round(t.bpm) : "—";
    const key = document.createElement("span"); key.className = "r"; key.append(keyChip(t.camelot));
    const en = document.createElement("span"); en.className = "r"; en.append(energyBar(t.energy_score));
    const gn = document.createElement("span"); gn.className = "gn";
    gn.textContent = t.genre || t.top_genre || "";
    r.append(idx, nm, bpm, key, en, gn);
    r.addEventListener("click", () => { setSelected(t.content_id); onSelect(t); });
    return r;
  }

  function setSelected(id) { selectedId = id; render(); }

  let scheduled = false;
  container.addEventListener("scroll", () => {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => { scheduled = false; render(); });
  });
  window.addEventListener("resize", () => render());

  return {
    setData(list) { all = list || []; buildIndex(); recompute(); },
    setQuery(q) { query = (q || "").toLowerCase().trim(); recompute(); },
    setSort(key) {
      if (sortKey === key) sortDir = -sortDir; else { sortKey = key; sortDir = 1; }
      recompute();
      return { key: sortKey, dir: sortDir };
    },
    setSelected,
    getSelectedId() { return selectedId; },
    getSelectedTrack() { return all.find((t) => t.content_id === selectedId) || null; },
    render,
  };
}
