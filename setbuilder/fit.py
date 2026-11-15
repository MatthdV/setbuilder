"""Deux dimensions de scoring contextuelles au slot :
- `energy_fit` : écart entre l'énergie du candidat et la cible de la courbe.
- `tag_bonus` : cohérence My Tag (moment / ambiance) candidat vs slot.
"""

_ENERGY_SPAN = 9.0  # énergie 1-10 → écart max de 9


def energy_fit(cand_energy: int | None, target: float) -> tuple[str, float]:
    """`(label, sous-score 0..1)`. Énergie absente → neutre ("énergie n/a", 0.5)."""
    if cand_energy is None:
        return "énergie n/a", 0.5
    gap = abs(cand_energy - target)
    score = max(0.0, 1.0 - gap / _ENERGY_SPAN)
    if cand_energy < target - 0.5:
        arrow = "↗"  # candidat sous la cible : il faut monter
    elif cand_energy > target + 0.5:
        arrow = "↘"
    else:
        arrow = "="
    return f"énergie {arrow}", score


def tag_bonus(
    cand_moment: str | None,
    cand_ambiance: str | None,
    slot_moment: str | None,
    slot_ambiance: str | None,
) -> tuple[str, float]:
    """`(label, sous-score 0..1)` : fraction des champs voulus du slot que le
    candidat retrouve. Candidat sans tag, ou slot sans voeu → neutre 0.5.
    """
    if cand_moment is None and cand_ambiance is None:
        return "ambiance n/a", 0.5
    wanted = [(slot_moment, cand_moment, "moment"), (slot_ambiance, cand_ambiance, "ambiance")]
    wanted = [(w, c, name) for (w, c, name) in wanted if w is not None]
    if not wanted:
        return "ambiance n/a", 0.5
    hits = [name for (w, c, name) in wanted if w == c]
    score = len(hits) / len(wanted)
    label = "ambiance " + (", ".join(f"{n}✓" for n in hits) if hits else "✗")
    return label, score
