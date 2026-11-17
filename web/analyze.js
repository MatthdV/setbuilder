// Analysis panel. Renders job state from /analyze/pending + /analyze/status.
// No business logic client-side. DOM-built, no innerHTML with server strings.

function _el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// el: container ; pend: {pending, total} ; status: /analyze/status object ;
// onStart: button click callback.
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
    el.append(_el("div", "an-head", `Analyzing — ${i}/${tot}`), bar);
    el.append(_el("div", "an-meta",
      `analyzed ${status.analyzed || 0} · skipped ${status.skipped || 0} · ` +
      `missing ${status.missing || 0} · failed ${status.failed || 0}`));
    const fails = status.failures || [];
    if (fails.length) {
      const det = _el("details", "an-fails");
      det.append(_el("summary", null, `${fails.length} failure(s)`));
      fails.forEach(([cid, msg]) => det.append(_el("div", "an-meta", `${cid}: ${msg}`)));
      el.append(det);
    }
    return;
  }

  // non-running: idle | stale | done | error -> banner (optional) + button
  if (state === "error") {
    // Server message may be non-English; show a generic English banner.
    el.append(_el("div", "an-banner err", "Analysis error — check the batch and retry."));
  } else if (state === "stale") {
    el.append(_el("div", "an-banner warn", "Previous job interrupted — safe to relaunch."));
  } else if (state === "done") {
    el.append(_el("div", "an-banner ok",
      `Analysis done: ${status.analyzed || 0} analyzed, ${status.failed || 0} failed.`));
  }

  const failed = (pend && pend.failed) || 0;
  const btn = _el("button", "btn", pending > 0
    ? `Analyze ${pending} new tracks`
    : (total ? "Library up to date" : "No analyzable tracks"));
  btn.disabled = pending === 0;
  btn.addEventListener("click", onStart);
  el.append(btn);
  if (failed > 0) el.append(_el("div", "an-meta", `${failed} track(s) failed analysis and are skipped.`));
}
