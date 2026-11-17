// Camelot wheel color + shared chip/energy builders. The ONLY place that maps a
// key to a color. DOM-built, no innerHTML (security pattern of the front).

function camelotColor(code) {
  if (!code) return null;
  const n = parseInt(code, 10);
  if (!n || n < 1 || n > 12) return null;
  const ab = String(code).slice(-1).toUpperCase();
  const hue = ((n - 1) * 30 + 190) % 360;   // wheel, offset so 1 starts cool
  const l = ab === "B" ? 62 : 52;           // B a touch lighter than A
  return `hsl(${hue} 58% ${l}%)`;
}

// Camelot key chip. Unknown/missing key -> neutral "na" chip.
function keyChip(code) {
  const s = document.createElement("span");
  s.className = "key";
  const c = camelotColor(code);
  if (c) {
    s.textContent = code;
    s.style.background = c;
  } else {
    s.textContent = code || "—";
    s.classList.add("na");
  }
  return s;
}

// Hard LED energy bar + numeric. e is 0..10 or null/undefined.
function energyBar(e) {
  const w = document.createElement("span");
  w.className = "en";
  const bar = document.createElement("span");
  bar.className = "bar";
  const known = e != null && !Number.isNaN(e);
  const v = known ? Math.max(0, Math.min(10, Math.round(e))) : 0;
  for (let i = 0; i < 10; i++) {
    const b = document.createElement("i");
    if (known && i < v) b.className = "on" + (i >= 7 ? " hi" : "");
    bar.append(b);
  }
  const n = document.createElement("span");
  n.className = "n";
  n.textContent = known ? String(v).padStart(2, "0") : "--";
  w.append(bar, n);
  return w;
}
