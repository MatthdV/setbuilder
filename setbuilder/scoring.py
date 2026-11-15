"""Agrégation explicable des dimensions de compatibilité en un score 0-100.

Chaque dimension rend `(label, sous-score 0..1)`. Une dimension non applicable
(donnée manquante : pas de clé, pas de BPM, pas d'embedding, pas de tag, ou
premier slot sans précédent) rend un score neutre et est **exclue** de la
moyenne pondérée, dont les poids sont renormalisés sur les seules dimensions
applicables. Ainsi un match parfait sur les dimensions connues n'est pas
pénalisé par une vibe absente.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from setbuilder.bpm import bpm_compat
from setbuilder.fit import energy_fit, tag_bonus
from setbuilder.harmony import camelot_compat
from setbuilder.vibe import vibe_score

SCORING_VERSION = "scoring-v1"

# Labels neutres émis quand une dimension n'a pas l'info nécessaire.
_NA_LABELS = {"key inconnue", "BPM inconnu", "vibe n/a", "ambiance n/a", "énergie n/a"}


@dataclass(frozen=True)
class Weights:
    key: float = 0.30
    bpm: float = 0.20
    energy: float = 0.20
    vibe: float = 0.20
    ambiance: float = 0.10


DEFAULT_WEIGHTS = Weights()


@dataclass
class Candidate:
    content_id: str
    title: str | None
    artist: str | None
    bpm: float | None
    camelot: str | None
    energy: int | None
    moment: str | None
    ambiance: str | None
    embedding: np.ndarray | None


@dataclass
class SlotContext:
    prev: Candidate | None
    target_energy: float
    slot_moment: str | None = None
    slot_ambiance: str | None = None


@dataclass
class ScoreBreakdown:
    content_id: str
    score: int  # 0-100
    dimensions: dict[str, tuple[str, float]] = field(default_factory=dict)


def score_candidate(
    cand: Candidate, ctx: SlotContext, weights: Weights = DEFAULT_WEIGHTS
) -> ScoreBreakdown:
    prev = ctx.prev
    dims: dict[str, tuple[str, float]] = {
        "key": camelot_compat(prev.camelot if prev else None, cand.camelot),
        "bpm": bpm_compat(prev.bpm if prev else None, cand.bpm),
        "energy": energy_fit(cand.energy, ctx.target_energy),
        "vibe": vibe_score(prev.embedding if prev else None, cand.embedding),
        "ambiance": tag_bonus(cand.moment, cand.ambiance, ctx.slot_moment, ctx.slot_ambiance),
    }
    w = {
        "key": weights.key, "bpm": weights.bpm, "energy": weights.energy,
        "vibe": weights.vibe, "ambiance": weights.ambiance,
    }
    active = {k: v[1] for k, v in dims.items() if v[0] not in _NA_LABELS}
    total_w = sum(w[k] for k in active)
    if total_w > 0:
        raw = sum(w[k] * active[k] for k in active) / total_w
    else:  # tout est n/a (candidat sans aucune donnée) : neutre
        raw = 0.5
    return ScoreBreakdown(cand.content_id, round(100 * raw), dims)
