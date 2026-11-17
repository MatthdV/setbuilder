// Audio preview. One shared <audio>; any ▶ button calls previewToggle(cid).
// Starts at 35% for a mid-track listen. Seek: drag the bar, click a 10% tick,
// ←/→ = ±15 s (Shift: ±60 s), keys 0-9 = jump to 0-90 %.
let _loadToken = 0;
const player = { audio: new Audio(), cid: null, loadedCid: null, titleOf: null, onChange: () => {} };
player.audio.preload = "none";

function isPlaying(cid) { return player.cid === cid && !player.audio.paused; }

async function previewToggle(cid) {
  const a = player.audio;
  if (player.cid === cid && player.loadedCid === cid) { a.paused ? a.play().catch(() => {}) : a.pause(); return; }
  player.cid = cid;
  const token = ++_loadToken;
  player.loadedCid = null;
  a.pause();
  _renderPlayer(true);
  document.getElementById("pl-time").textContent = "loading…";  // AIFF: first play converts the file once
  player.onChange();
  const dur = (typeof durOf === "function" && durOf(cid)) || 0;
  const start = Math.floor(dur * 0.35);
  try {
    const info = await (await fetch(`/tracks/${encodeURIComponent(cid)}/preview-info`)).json();
    if (token !== _loadToken) return;  // another track was chosen meanwhile
    if (info.detail) throw new Error(info.detail);
    player.loadedCid = cid;
    a.src = `/tracks/${encodeURIComponent(cid)}/preview`;
    // every format is seekable over the WHOLE track (non-native ones are served as a cached full mp3)
    if (start) a.addEventListener("loadedmetadata", () => { a.currentTime = start; }, { once: true });
    await a.play();
  } catch (e) {
    if (token !== _loadToken) return;  // stale failure must not clear the newer track
    player.cid = null; player.loadedCid = null;
    toast("Cannot play this track (file unreachable — drive unplugged? — or unsupported).", true);
    _renderPlayer(false);
  }
  player.onChange();
}

function _fmt(t) { t = Math.max(0, Math.floor(t || 0)); return Math.floor(t / 60) + ":" + String(t % 60).padStart(2, "0"); }

function _renderPlayer(show) {
  const bar = document.getElementById("player");
  if (!bar) return;
  bar.hidden = !show && !player.cid;
  if (player.cid) {
    document.getElementById("pl-title").textContent = player.titleOf ? player.titleOf(player.cid) : player.cid;
    document.getElementById("pl-btn").textContent = player.audio.paused ? "▶" : "❚❚";
  }
}

function initPlayer(titleOf, onChange) {
  player.titleOf = titleOf; player.onChange = onChange;
  const a = player.audio, seek = document.getElementById("pl-seek");
  document.getElementById("pl-btn").addEventListener("click", () => { if (player.cid) previewToggle(player.cid); });
  document.getElementById("pl-stop").addEventListener("click", () => { a.pause(); a.removeAttribute("src"); player.cid = null; player.loadedCid = null; _renderPlayer(false); onChange(); });
  seek.addEventListener("input", () => { if (a.duration) a.currentTime = (seek.value / 1000) * a.duration; });
  a.addEventListener("timeupdate", () => {
    if (a.duration) seek.value = Math.round((a.currentTime / a.duration) * 1000);
    document.getElementById("pl-time").textContent = _fmt(a.currentTime) + " / " + _fmt(a.duration);
  });
  for (const ev of ["play", "pause", "ended"]) a.addEventListener(ev, () => { _renderPlayer(true); onChange(); });
  const jump = (dt) => { if (a.duration) a.currentTime = Math.max(0, Math.min(a.duration - 0.5, a.currentTime + dt)); };
  document.addEventListener("keydown", (e) => {
    if (!player.cid || /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
    if (e.code === "ArrowRight") { e.preventDefault(); jump(e.shiftKey ? 60 : 15); }
    else if (e.code === "ArrowLeft") { e.preventDefault(); jump(e.shiftKey ? -60 : -15); }
    else if (/^Digit[0-9]$/.test(e.code) && a.duration) { a.currentTime = (Number(e.code.slice(5)) / 10) * a.duration; }
  });
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && player.cid && !/INPUT|SELECT|TEXTAREA|BUTTON/.test(e.target.tagName)) {
      e.preventDefault(); previewToggle(player.cid);
    }
  });
}
