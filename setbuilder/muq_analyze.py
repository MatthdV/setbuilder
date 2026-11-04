"""Embedding de vibe MuQ (1024-d, mean-pooled par track).

`mean_pool` et `split_segments` sont purs et testés unitairement ;
`analyze_muq` charge torch/muq paresseusement (extra `analysis`).
"""

import os

import numpy as np

from setbuilder.errors import AnalysisUnavailableError

MODEL_ID = "OpenMuQ/MuQ-large-msd-iter"
MUQ_SR = 24000          # MuQ attend du 24 kHz (l'audio d'analyse est en 16 kHz)
SEGMENT_SECONDS = 60    # borne la mémoire sur les longs morceaux


class MuQUnavailableError(AnalysisUnavailableError):
    """MuQ / poids HF indisponibles (extra absent, ou hors-ligne au premier run)."""


def mean_pool(hidden: np.ndarray) -> np.ndarray | None:
    """(frames, dim) -> (dim,). None si 0 frame, forme invalide ou valeurs non finies."""
    if hidden.ndim != 2 or hidden.shape[0] == 0:
        return None
    pooled = hidden.mean(axis=0)
    if not np.isfinite(pooled).all():
        return None
    return pooled


def split_segments(audio: np.ndarray, seg_len: int, min_len: int) -> list[np.ndarray]:
    """Découpe en segments de `seg_len` ; un reste < min_len est fusionné au segment précédent."""
    n = len(audio)
    if n == 0:
        return []
    segs = [audio[i:i + seg_len] for i in range(0, n, seg_len)]
    if len(segs) > 1 and len(segs[-1]) < min_len:
        last = segs.pop()
        segs[-1] = np.concatenate([segs[-1], last])
    return [s for s in segs if len(s) >= min_len] if len(segs) > 1 else (
        segs if len(segs[0]) >= min_len else [])


_model = None
_device = None


def _load():
    global _model, _device
    if _model is not None:
        return _model, _device
    try:
        import torch
        from muq import MuQ
    except ImportError as e:
        raise MuQUnavailableError(
            "muq/torch absents : installe l'extra avec `uv sync --extra analysis`."
        ) from e
    try:
        model = MuQ.from_pretrained(MODEL_ID)
    except Exception as e:  # réseau HF, cache absent, version transformers incompatible
        raise MuQUnavailableError(
            f"Impossible de charger {MODEL_ID} ({type(e).__name__}: {e}). Premier run hors-ligne ? "
            "Les poids HF se téléchargent au premier run. Vérifie aussi transformers==4.44.2 "
            "(MuQ casse avec 5.x)."
        ) from e
    _device = os.environ.get("SETBUILDER_DEVICE", "cpu")  # "mps" possible, non défaut (ops instables)
    _model = model.to(_device).eval()
    return _model, _device


def analyze_muq(audio: np.ndarray) -> np.ndarray | None:
    """Embedding (1024,) d'un signal 16 kHz mono, ou None si trop court / non fini."""
    import torch
    from scipy.signal import resample_poly

    model, device = _load()
    wav = resample_poly(audio, 3, 2).astype(np.float32)  # 16 kHz -> 24 kHz
    frames = []
    with torch.no_grad():
        for seg in split_segments(wav, MUQ_SR * SEGMENT_SECONDS, min_len=MUQ_SR):
            out = model(torch.from_numpy(seg)[None].to(device), output_hidden_states=True)
            frames.append(out.last_hidden_state[0].float().cpu().numpy())
    if not frames:
        return None
    return mean_pool(np.concatenate(frames, axis=0))
