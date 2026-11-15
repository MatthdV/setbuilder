// Cartes de suggestions : score + detail par dimension (ScoreBreakdown).
// onPlace(content_id). Elements construits en DOM (pas d'innerHTML utilisateur).
const _NA = new Set(["key inconnue", "BPM inconnu", "vibe n/a", "ambiance n/a", "énergie n/a"]);

function renderSuggestions(listEl, breakdowns, titleOf, onPlace) {
  listEl.textContent = "";
  if (!breakdowns.length) {
    const p = document.createElement("div");
    p.className = "galaxy-empty";
    p.textContent = "Aucune suggestion (librairie vide ou non analysée).";
    listEl.append(p);
    return;
  }
  breakdowns.forEach((b) => {
    const card = document.createElement("div");
    card.className = "sugg-card";

    const head = document.createElement("div");
    head.className = "sugg-head";
    const title = document.createElement("span");
    title.textContent = titleOf(b.content_id);
    const score = document.createElement("span");
    score.className = "sugg-score";
    score.textContent = Math.round(b.score);
    head.append(title, score);

    const dims = document.createElement("div");
    dims.className = "sugg-dims";
    Object.entries(b.dimensions).forEach(([, pair]) => {
      const [label] = pair;
      const chip = document.createElement("span");
      chip.className = "dim" + (_NA.has(label) ? " na" : "");
      chip.textContent = label;
      dims.append(chip);
    });

    const actions = document.createElement("div");
    actions.className = "sugg-actions";
    const place = document.createElement("button");
    place.textContent = "Poser";
    place.addEventListener("click", () => onPlace(b.content_id));
    actions.append(place);

    card.append(head, dims, actions);
    listEl.append(card);
  });
}

// Affiche l'ImpactReport d'un morceau force (warnings).
function renderImpact(el, impact) {
  if (!impact || !impact.warnings || !impact.warnings.length) {
    el.classList.remove("show");
    el.textContent = "";
    return;
  }
  el.textContent = "Impact du forçage : " + impact.warnings.join(" · ");
  el.classList.add("show");
}
