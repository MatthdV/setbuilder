// Galaxy 2D : nuage UMAP + chemin du set (slots remplis dans l'ordre) +
// marqueur distinct pour les forces. Survol = infobulle titre/artiste.
// Lib non analysee (points vides) -> etat vide lisible.
function drawGalaxy(canvas, points, setPath, forcedIds, titleOf) {
  const emptyEl = document.getElementById("galaxy-empty");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  if (!points.length) {
    canvas.style.display = "none";
    if (emptyEl) emptyEl.style.display = "block";
    return;
  }
  canvas.style.display = "block";
  if (emptyEl) emptyEl.style.display = "none";

  const pad = 16;
  const xs = points.map((p) => p.umap_x), ys = points.map((p) => p.umap_y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const sx = (x) => pad + ((x - minX) / (maxX - minX || 1)) * (canvas.width - 2 * pad);
  const sy = (y) => pad + ((y - minY) / (maxY - minY || 1)) * (canvas.height - 2 * pad);

  const byId = {};
  points.forEach((p) => { byId[p.content_id] = p; });
  const forced = new Set(forcedIds || []);

  // nuage
  points.forEach((p) => {
    ctx.beginPath();
    ctx.arc(sx(p.umap_x), sy(p.umap_y), 2.5, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(154,161,169,0.45)";
    ctx.fill();
  });

  // chemin du set (ordre des slots remplis)
  const pathPts = (setPath || []).map((cid) => byId[cid]).filter(Boolean);
  if (pathPts.length > 1) {
    ctx.beginPath();
    pathPts.forEach((p, i) => {
      const X = sx(p.umap_x), Y = sy(p.umap_y);
      i === 0 ? ctx.moveTo(X, Y) : ctx.lineTo(X, Y);
    });
    ctx.strokeStyle = "#d97757";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  // morceaux du chemin : point accentue ; force = rouge hors flux
  pathPts.forEach((p) => {
    ctx.beginPath();
    ctx.arc(sx(p.umap_x), sy(p.umap_y), 4, 0, Math.PI * 2);
    ctx.fillStyle = forced.has(p.content_id) ? "#e0614a" : "#d97757";
    ctx.fill();
  });

  // infobulle au survol
  canvas.onmousemove = (ev) => {
    const rect = canvas.getBoundingClientRect();
    const mx = (ev.clientX - rect.left) * (canvas.width / rect.width);
    const my = (ev.clientY - rect.top) * (canvas.height / rect.height);
    let hit = null;
    for (const p of points) {
      const dx = sx(p.umap_x) - mx, dy = sy(p.umap_y) - my;
      if (dx * dx + dy * dy < 36) { hit = p; break; }
    }
    canvas.title = hit ? titleOf(hit.content_id) : "";
  };
}
