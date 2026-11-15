"""Formule energy_score (v1)."""

ENERGY_FORMULA_VERSION = "energy-v1"
_W_AROUSAL = 0.7
_W_LOUDNESS = 0.3


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def energy_score(arousal: float, loudness_norm: float) -> int:
    """Énergie 1-10 : 70 % arousal (EffNet) + 30 % loudness normalisé, entrées clampées à [0,1]."""
    mix = _W_AROUSAL * _clamp01(arousal) + _W_LOUDNESS * _clamp01(loudness_norm)
    return max(1, min(10, round(1 + 9 * mix)))
