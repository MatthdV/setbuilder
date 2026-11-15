"""Compatibilité de tempo entre le morceau précédent et un candidat.

Tient compte du mix en demi / double temps (64 ↔ 128 BPM se mixe) en
retenant l'appariement d'octave le plus proche.
"""


def bpm_compat(prev: float | None, cand: float | None, tolerance: float = 0.06) -> tuple[str, float]:
    """`(label, sous-score 0..1)`. Entrée absente → neutre ("BPM inconnu", 0.5).

    Score = 1 à tempo égal, décroissance linéaire jusqu'à 0 à un écart relatif
    de `4 * tolerance` (±24 % par défaut), après prise en compte du demi/double.
    """
    if not prev or not cand:
        return "BPM inconnu", 0.5
    r0 = cand / prev
    # r0 : même tempo ; r0*2 : candidat joué en double ; r0/2 : en demi.
    options = ((r0, ""), (r0 * 2, " (x2)"), (r0 / 2, " (½)"))
    ratio, suffix = min(options, key=lambda o: abs(o[0] - 1.0))
    drift = abs(ratio - 1.0)
    score = max(0.0, 1.0 - drift / (4 * tolerance))
    label = f"{(ratio - 1.0) * 100:+.1f}% BPM{suffix}"
    return label, score
