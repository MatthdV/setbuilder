// Timeline des slots : ancres (accent), vide selectionne, force en rouge.
// Clic -> onSelect(position). Pas d'innerHTML avec des chaines utilisateur.
function drawTimeline(el, slots, selectedPos, onSelect) {
  el.textContent = "";
  slots.forEach((s) => {
    const d = document.createElement("div");
    d.className = "slot";
    if (s.content_id) d.classList.add("filled");
    if (s.is_anchor) d.classList.add("anchor");
    if (s.is_forced) d.classList.add("forced");
    if (s.position === selectedPos) d.classList.add("selected");

    const pos = document.createElement("span");
    pos.className = "pos";
    pos.textContent = s.position + 1;
    const cid = document.createElement("span");
    cid.className = "cid";
    cid.textContent = s.content_id ? s.content_id.slice(0, 6) : "—";

    d.append(pos, cid);
    d.addEventListener("click", () => onSelect(s.position));
    el.append(d);
  });
}
