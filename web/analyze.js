// Panneau d'analyse (plan 6). Rend l'état du job depuis /analyze/pending +
// /analyze/status ; aucune logique métier côté client. Pas d'innerHTML pour des
// données venues du serveur (pattern plan 5).

function _el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// el : conteneur ; pend : {pending, total} ; status : objet /analyze/status ;
// onStart : callback clic bouton.
function renderAnalyze(el, pend, status, onStart) {
  el.textContent = "";
  const state = (status && status.state) || "idle";
  const pending = (pend && pend.pending) || 0;
  const total = (pend && pend.total) || 0;

  if (state === "running") {
    const i = status.i || 0;
    const tot = status.total || 0;
    const bar = _el("div", "an-bar");
    const fill = _el("div", "an-bar-fill");
    fill.style.width = (tot ? Math.round((i / tot) * 100) : 0) + "%";
    bar.append(fill);
    el.append(_el("div", "an-head", `Analyse en cours — ${i}/${tot}`), bar);
    el.append(_el("div", "meta",
      `analysés ${status.analyzed || 0} · sautés ${status.skipped || 0} · ` +
      `introuvables ${status.missing || 0} · échecs ${status.failed || 0}`));
    const fails = status.failures || [];
    if (fails.length) {
      const det = _el("details", "an-fails");
      det.append(_el("summary", null, `${fails.length} échec(s)`));
      fails.forEach(([cid, msg]) => det.append(_el("div", "meta", `${cid} : ${msg}`)));
      el.append(det);
    }
    return;
  }

  // états non-running : idle | stale | done | error -> bouton + bandeau éventuel
  if (state === "error") {
    el.append(_el("div", "an-banner err", status.message || "Erreur d'analyse."));
  } else if (state === "stale") {
    el.append(_el("div", "an-banner warn", "Job précédent interrompu — relance possible."));
  } else if (state === "done") {
    el.append(_el("div", "an-banner ok",
      `Analyse terminée : ${status.analyzed || 0} analysés, ${status.failed || 0} échecs.`));
  }

  const btn = _el("button", "primary", pending > 0
    ? `Analyser ${pending} nouveaux morceaux`
    : (total ? "Librairie à jour" : "Aucun morceau analysable"));
  btn.disabled = pending === 0;
  btn.addEventListener("click", onStart);
  el.append(btn);
}
