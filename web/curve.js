// Courbe d'energie : cible (depuis curve_points) vs reelle (energie des
// morceaux places). Bandeau d'alerte si decrochage (ecart > seuil).
const CURVE_W = 600, CURVE_H = 160, CURVE_PAD = 8, DROP_THRESHOLD = 3.0;

function _yFromEnergy(e) {
  // energie 0..10 -> y (haut = haute energie)
  const t = Math.max(0, Math.min(10, e)) / 10;
  return CURVE_H - CURVE_PAD - t * (CURVE_H - 2 * CURVE_PAD);
}

function _targetAt(points, pos) {
  // interpolation lineaire clampee sur curve_points [[pos,energy],...]
  if (!points.length) return 5;
  const sorted = [...points].sort((a, b) => a[0] - b[0]);
  if (pos <= sorted[0][0]) return sorted[0][1];
  if (pos >= sorted[sorted.length - 1][0]) return sorted[sorted.length - 1][1];
  for (let i = 1; i < sorted.length; i++) {
    if (pos <= sorted[i][0]) {
      const [p0, e0] = sorted[i - 1], [p1, e1] = sorted[i];
      const f = (pos - p0) / (p1 - p0);
      return e0 + f * (e1 - e0);
    }
  }
  return sorted[sorted.length - 1][1];
}

// slots: [{position, content_id}], realEnergies: {content_id: energy|null}
function drawCurve(svg, points, slots, realEnergies) {
  const n = slots.length;
  const x = (i) => CURVE_PAD + (n <= 1 ? 0 : (i / (n - 1)) * (CURVE_W - 2 * CURVE_PAD));
  const posOf = (i) => (n <= 1 ? 0 : i / (n - 1));

  // cible : polyline lisse echantillonnee
  const targetPts = [];
  for (let i = 0; i < n; i++) targetPts.push(`${x(i)},${_yFromEnergy(_targetAt(points, posOf(i)))}`);

  // reelle : seulement les slots remplis dont l'energie est connue
  const realPts = [];
  let maxDrop = 0;
  for (let i = 0; i < n; i++) {
    const cid = slots[i].content_id;
    const e = cid ? realEnergies[cid] : null;
    if (e != null) {
      realPts.push(`${x(i)},${_yFromEnergy(e)}`);
      maxDrop = Math.max(maxDrop, Math.abs(e - _targetAt(points, posOf(i))));
    }
  }

  svg.innerHTML = `
    <polyline points="${targetPts.join(" ")}" fill="none"
      stroke="var(--curve-target)" stroke-width="2" />
    ${realPts.length > 1
      ? `<polyline points="${realPts.join(" ")}" fill="none"
          stroke="var(--curve-real)" stroke-width="2" stroke-dasharray="4 3" />`
      : ""}
    ${realPts.map((p) => { const [cx, cy] = p.split(","); return `<circle cx="${cx}" cy="${cy}" r="3" fill="var(--curve-real)" />`; }).join("")}
  `;

  const alert = document.getElementById("curve-alert");
  if (maxDrop > DROP_THRESHOLD) {
    alert.textContent = `Décrochage : écart cible/réel jusqu'à ${maxDrop.toFixed(1)} points d'énergie.`;
    alert.classList.add("show");
  } else {
    alert.classList.remove("show");
  }
}
