// Slots ledger: coordinate SLOT_NN, track title (not a content_id slice),
// Camelot chip, anchor/forced markers, empty = hatched. Click -> onSelect(pos).
// DOM-built, no innerHTML with server/user strings.
function drawTimeline(el, slots, selectedPos, onSelect, titleOf, keyOf) {
  el.textContent = "";
  slots.forEach((s) => {
    const d = document.createElement("div");
    d.className = "st";
    const filled = !!s.content_id;
    if (!filled) d.classList.add("empty");
    if (s.is_anchor) d.classList.add("anchor");
    if (s.is_forced) d.classList.add("forced");
    if (s.position === selectedPos) d.classList.add("selected");

    const co = document.createElement("div");
    co.className = "co";
    co.textContent = "SLOT_" + String(s.position + 1).padStart(2, "0");

    const nm = document.createElement("div");
    nm.className = "snm";
    nm.textContent = filled ? titleOf(s.content_id) : "— empty —";

    d.append(co, nm);
    if (filled) d.append(keyChip(keyOf(s.content_id)));

    d.addEventListener("click", () => onSelect(s.position));
    el.append(d);
  });
}
