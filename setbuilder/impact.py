"""Feedback d'impact d'un morceau forcé hors suggestions.

Réutilise les dimensions du plan 3 pour mesurer ce que le morceau fait à la
courbe (énergie) et aux enchaînements (key avec les voisins, saut de BPM), et
remonte des `warnings` lisibles. Jamais bloquant : c'est de l'information.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from setbuilder.bpm import bpm_compat
from setbuilder.fit import energy_fit
from setbuilder.harmony import camelot_compat as _classic_compat
from setbuilder.keymoves import key_move
from setbuilder.scoring import Candidate

# Labels neutres (donnée manquante) : n'émettent jamais de warning.
_NA_LABELS = {"key inconnue", "BPM inconnu", "énergie n/a"}
_KEY_FLOOR = 0.3
_ENERGY_FLOOR = 0.4
_BPM_FLOOR = 0.4


@dataclass
class ImpactReport:
    energy: tuple[str, float]
    key_prev: tuple[str, float]
    key_next: tuple[str, float]
    bpm_prev: tuple[str, float]
    warnings: list[str] = field(default_factory=list)


def camelot_compat(a, b):
    """Harmonie classique, mais un enchaînement prévu par la table (boost/drop/mood)
    n'est jamais un « clash »."""
    label, score = _classic_compat(a, b)
    if score < _KEY_FLOOR:
        move = key_move(a, b)
        if move is not None:
            return move.label, 0.6
    return label, score


def _applicable(dim: tuple[str, float]) -> bool:
    return dim[0] not in _NA_LABELS


def forced_impact(
    forced: Candidate,
    prev: Candidate | None,
    next_: Candidate | None,
    target_energy: float,
) -> ImpactReport:
    energy = energy_fit(forced.energy, target_energy)
    key_prev = camelot_compat(prev.camelot if prev else None, forced.camelot)
    key_next = camelot_compat(forced.camelot, next_.camelot if next_ else None)
    bpm_prev = bpm_compat(prev.bpm if prev else None, forced.bpm)

    warnings: list[str] = []
    if _applicable(energy) and energy[1] < _ENERGY_FLOOR:
        warnings.append(f"énergie loin de la cible ({energy[0]})")
    if _applicable(key_prev) and key_prev[1] < _KEY_FLOOR:
        warnings.append(f"clash de key avec le précédent ({key_prev[0]})")
    if _applicable(key_next) and key_next[1] < _KEY_FLOOR:
        warnings.append(f"clash de key avec le suivant ({key_next[0]})")
    if _applicable(bpm_prev) and bpm_prev[1] < _BPM_FLOOR:
        warnings.append(f"saut de BPM depuis le précédent ({bpm_prev[0]})")

    return ImpactReport(energy, key_prev, key_next, bpm_prev, warnings)
