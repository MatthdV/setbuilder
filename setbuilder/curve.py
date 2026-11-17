"""Courbe d'énergie cible du set : énergie voulue (1-10) à chaque position.

Position normalisée 0-1 (le mapping vers le temps ou l'index de slot selon le
mode du set vit dans la couche set, plan 4). Interpolation linéaire, position
clampée aux bornes (pas d'extrapolation).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnergyCurve:
    points: tuple[tuple[float, float], ...]  # triés par position, positions uniques

    @classmethod
    def from_points(cls, points: list[tuple[float, float]]) -> EnergyCurve:
        if not points:
            raise ValueError("la courbe d'énergie exige au moins un point")
        dedup: dict[float, float] = {}
        for pos, energy in points:
            dedup[float(pos)] = float(energy)
        ordered = tuple(sorted(dedup.items()))
        return cls(ordered)

    def target_at(self, pos: float) -> float:
        """Énergie cible à `pos` (clampé à [première position, dernière position])."""
        pts = self.points
        if pos <= pts[0][0]:
            return pts[0][1]
        if pos >= pts[-1][0]:
            return pts[-1][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= pos <= x1:
                t = (pos - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        return pts[-1][1]  # inatteignable, garde-fou


# Courbes cibles par type de set (position 0-1, énergie 0-10). Source unique :
# l'API les applique à la création, le front n'envoie que le type.
PRESETS: dict[str, list[tuple[float, float]]] = {
    # Montée douce : on pose l'ambiance sans brûler la piste.
    "warmup": [(0.0, 2.0), (0.5, 3.5), (1.0, 5.0)],
    # Montée, pic, plateau haut.
    "main": [(0.0, 5.0), (0.3, 7.0), (0.65, 9.0), (1.0, 8.0)],
    # Pic tenu puis descente vers la fin.
    "closing": [(0.0, 8.0), (0.4, 9.0), (1.0, 4.0)],
    # After : bas/moyen, hypnotique, sans gros pic.
    "after": [(0.0, 4.0), (0.4, 5.5), (0.8, 5.0), (1.0, 3.0)],
}
