// Suggestion cards: score + per-dimension breakdown (ScoreBreakdown). onPlace,
// onForce(content_id). DOM-built, no innerHTML with server/user strings.
// NOTE: dimension labels come from the backend scoring layer (currently French).
// We translate the known "unknown/na" variants to English here; any other label
// is backend DATA shown verbatim. _NA greys out the unknown variants.
const _DIM_EN = {
  "key inconnue": "key n/a",
  "BPM inconnu": "BPM n/a",
  "vibe n/a": "vibe n/a",
  "ambiance n/a": "mood n/a",
  "énergie n/a": "energy n/a",
};
const _NA = new Set(Object.keys(_DIM_EN));

// Backend labels are French; translate the known shapes, pass anything else through.
function trLabel(l) {
  if (_DIM_EN[l]) return _DIM_EN[l];
  return String(l)
    .replace("key ✓ (même)", "key ✓ (same)")
    .replace(/^énergie /, "energy ")
    .replace(/^ambiance /, "mood ");
}
function trWarning(w) {
  const m = /^(.*?) \((.*)\)$/.exec(w);
  const label = m ? trLabel(m[2]) : "";
  const head = m ? m[1] : w;
  const map = [
    [/^énergie loin de la cible/, "energy far from target"],
    [/^clash de key avec le précédent/, "key clash with previous"],
    [/^clash de key avec le suivant/, "key clash with next"],
    [/^saut de BPM depuis le précédent/, "BPM jump from previous"],
  ];
  for (const [re, en] of map) if (re.test(head)) return label ? `${en} (${label})` : en;
  return w;
}

function renderSuggestions(listEl, breakdowns, titleOf, keyOf, onPlace) {
  listEl.textContent = "";
  if (!breakdowns.length) {
    const p = document.createElement("div");
    p.className = "empty-note";
    p.textContent = "No suggestions (library empty or not analyzed).";
    listEl.append(p);
    return;
  }
  breakdowns.forEach((b) => {
    const card = document.createElement("div");
    card.className = "sugg-card";

    const head = document.createElement("div");
    head.className = "sugg-head";
    const left = document.createElement("div");
    left.className = "sugg-id";
    left.append(keyChip(keyOf(b.content_id)));
    const title = document.createElement("span");
    title.className = "sugg-title";
    title.textContent = titleOf(b.content_id);
    left.append(title);
    const score = document.createElement("span");
    score.className = "sugg-score";
    score.textContent = Math.round(b.score);
    head.append(left, score);

    const dims = document.createElement("div");
    dims.className = "sugg-dims";
    Object.entries(b.dimensions).forEach(([, pair]) => {
      const [label] = pair;
      const chip = document.createElement("span");
      chip.className = "dim" + (_NA.has(label) ? " na" : "");
      chip.textContent = trLabel(label);
      dims.append(chip);
    });

    const actions = document.createElement("div");
    actions.className = "sugg-actions";
    const place = document.createElement("button");
    place.className = "btn-sm";
    place.textContent = "Place";
    place.addEventListener("click", () => onPlace(b.content_id));
    actions.append(place);

    card.append(head, dims, actions);
    listEl.append(card);
  });
}

// ImpactReport of a forced track (warnings). textContent only.
function renderImpact(el, impact) {
  if (!impact || !impact.warnings || !impact.warnings.length) {
    el.classList.remove("show");
    el.textContent = "";
    return;
  }
  el.textContent = "Force impact: " + impact.warnings.map(trWarning).join(" · ");
  el.classList.add("show");
}
