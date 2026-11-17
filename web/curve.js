// Energy curve: target (from curve_points) vs actual (energy of placed tracks).
// SVG built from NUMERIC coordinates only — never inject labels / API / user
// strings into the template (DOM-safety rule of the front). Alert text is set
// via textContent, not innerHTML.
const CURVE_W = 360, CURVE_H = 96, CURVE_PAD = 6, DROP_THRESHOLD = 3.0;

function _yFromEnergy(e) {
  const t = Math.max(0, Math.min(10, e)) / 10;
  return CURVE_H - CURVE_PAD - t * (CURVE_H - 2 * CURVE_PAD);
}

function _targetAt(points, pos) {
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

// slots: [{position, content_id}], realEnergyOf: (content_id) -> energy|null
function drawCurve(svg, points, slots, realEnergyOf, posFn) {
  const n = slots.length;
  const x = (i) => CURVE_PAD + (n <= 1 ? 0 : (i / (n - 1)) * (CURVE_W - 2 * CURVE_PAD));
  const posOf = posFn || ((i) => (n <= 1 ? 0 : i / (n - 1)));

  const targetPts = [];
  for (let i = 0; i < n; i++) targetPts.push(`${x(i)},${_yFromEnergy(_targetAt(points, posOf(i)))}`);

  const realPts = [];
  let maxDrop = 0;
  for (let i = 0; i < n; i++) {
    const cid = slots[i].content_id;
    const e = cid ? realEnergyOf(cid) : null;
    if (e != null) {
      realPts.push(`${x(i)},${_yFromEnergy(e)}`);
      maxDrop = Math.max(maxDrop, Math.abs(e - _targetAt(points, posOf(i))));
    }
  }

  let grid = "";
  for (let g = 0; g <= 10; g += 2.5) {
    const y = _yFromEnergy(g);
    grid += `<line x1="0" y1="${y}" x2="${CURVE_W}" y2="${y}" stroke="var(--grid)" stroke-width="1" />`;
  }

  svg.innerHTML = `
    ${grid}
    <polyline points="${targetPts.join(" ")}" fill="none"
      stroke="var(--curve-target)" stroke-width="1.5" />
    ${realPts.length > 1
      ? `<polyline points="${realPts.join(" ")}" fill="none"
          stroke="var(--curve-real)" stroke-width="2" />`
      : ""}
    ${realPts.map((p) => { const [cx, cy] = p.split(","); return `<rect x="${cx - 2}" y="${cy - 2}" width="4" height="4" fill="var(--curve-real)" />`; }).join("")}
  `;

  const alert = document.getElementById("curve-alert");
  if (!alert) return;
  if (maxDrop > DROP_THRESHOLD) {
    alert.textContent = `Energy drop: target vs actual off by up to ${maxDrop.toFixed(1)} points.`;
    alert.classList.add("show");
  } else {
    alert.classList.remove("show");
  }
}
