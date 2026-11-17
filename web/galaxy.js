// Galaxy 2D: UMAP cloud colored by Camelot key + set path overlay (ordered
// filled slots) + distinct forced nodes. Rendered on load (independent of a set).
// DPR-correct backing store, resize redraw, pointer→canvas coord conversion,
// throttled hit test. Hover -> handlers.onHover(content_id|null, ev); click ->
// handlers.onSelect(content_id). No native title tooltip.
//
// byId: index from /library (content_id -> {camelot, ...}) for colors/hovercard.
function drawGalaxy(canvas, points, byId, setPath, forcedIds, handlers) {
  handlers = handlers || {};
  const emptyEl = document.getElementById("galaxy-empty");

  if (!points || !points.length) {
    canvas.style.display = "none";
    if (emptyEl) emptyEl.style.display = "block";
    canvas.onmousemove = canvas.onclick = canvas.onmouseleave = null;
    return;
  }
  canvas.style.display = "block";
  if (emptyEl) emptyEl.style.display = "none";

  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = rect.width, H = rect.height, pad = 16;

  const xs = points.map((p) => p.umap_x), ys = points.map((p) => p.umap_y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const sx = (x) => pad + ((x - minX) / (maxX - minX || 1)) * (W - 2 * pad);
  const sy = (y) => pad + ((y - minY) / (maxY - minY || 1)) * (H - 2 * pad);

  // project once (reused for draw + hit test)
  const proj = points.map((p) => ({ p, X: sx(p.umap_x), Y: sy(p.umap_y) }));
  const byProj = {};
  proj.forEach((o) => { byProj[o.p.content_id] = o; });

  ctx.clearRect(0, 0, W, H);

  // cloud colored by key
  proj.forEach(({ p, X, Y }) => {
    const meta = byId && byId[p.content_id];
    const c = meta && camelotColor(meta.camelot);
    ctx.globalAlpha = c ? 0.5 : 0.38;
    ctx.fillStyle = c || "#8c8c84";
    ctx.fillRect(X, Y, 1.8, 1.8);
  });
  ctx.globalAlpha = 1;

  // set path
  const forced = new Set(forcedIds || []);
  const pathPts = (setPath || []).map((cid) => byProj[cid]).filter(Boolean);
  if (pathPts.length > 1) {
    ctx.beginPath();
    pathPts.forEach((o, i) => { i ? ctx.lineTo(o.X, o.Y) : ctx.moveTo(o.X, o.Y); });
    ctx.strokeStyle = "#ff3b1f";
    ctx.lineWidth = 1;
    ctx.stroke();
  }
  pathPts.forEach((o) => {
    const meta = byId && byId[o.p.content_id];
    const c = (meta && camelotColor(meta.camelot)) || "#f4f4ef";
    ctx.fillStyle = forced.has(o.p.content_id) ? "#ff3b1f" : c;
    ctx.fillRect(o.X - 3.5, o.Y - 3.5, 7, 7);
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#0a0a09";
    ctx.strokeRect(o.X - 3.5, o.Y - 3.5, 7, 7);
  });

  function hitAt(clientX, clientY) {
    const r = canvas.getBoundingClientRect();
    const mx = (clientX - r.left) * (W / r.width);
    const my = (clientY - r.top) * (H / r.height);
    let best = null, bd = 49; // 7px radius squared
    for (const o of proj) {
      const dx = o.X - mx, dy = o.Y - my, d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = o; }
    }
    return best;
  }

  let scheduled = false, lastEv = null, inside = true;
  canvas.onmousemove = (ev) => {
    inside = true;
    lastEv = ev;
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      if (!inside) return; // pointer left before this frame ran
      const o = hitAt(lastEv.clientX, lastEv.clientY);
      if (handlers.onHover) handlers.onHover(o ? o.p.content_id : null, lastEv);
    });
  };
  canvas.onmouseleave = () => { inside = false; if (handlers.onHover) handlers.onHover(null, null); };
  canvas.onclick = (ev) => {
    const o = hitAt(ev.clientX, ev.clientY);
    if (o && handlers.onSelect) handlers.onSelect(o.p.content_id);
  };
}
