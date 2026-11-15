"""Compatibilité harmonique entre deux clés Camelot.

Roue Camelot : numéros 1-12, lettre A (mineur) ou B (majeur). Deux morceaux
mixent bien s'ils partagent la clé, sont voisins d'un cran (±1, même lettre),
relatifs (même numéro, lettre opposée), ou à +/-2 crans (energy boost).
"""

import re

_CAMELOT_RE = re.compile(r"^(1[0-2]|[1-9])([AB])$")


def _parse(code: str | None) -> tuple[int, str] | None:
    if not code:
        return None
    m = _CAMELOT_RE.match(code.strip().upper())
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def _wheel_distance(a: int, b: int) -> int:
    """Distance minimale sur la roue de 12 (1 et 12 sont adjacents)."""
    return min((a - b) % 12, (b - a) % 12)


def camelot_compat(a: str | None, b: str | None) -> tuple[str, float]:
    """`(label, sous-score 0..1)` pour l'enchaînement harmonique de a vers b.

    Entrée vide / absente / non Camelot → neutre ("key inconnue", 0.5).
    """
    pa, pb = _parse(a), _parse(b)
    if pa is None or pb is None:
        return "key inconnue", 0.5
    (na, la), (nb, lb) = pa, pb
    if na == nb and la == lb:
        return "key ✓ (même)", 1.0
    if na == nb:  # même numéro, lettre opposée → relatif majeur/mineur
        return "key relative", 0.85
    if la == lb:
        dist = _wheel_distance(na, nb)
        if dist == 1:
            return "key ±1", 0.9
        if dist == 2:
            return "key ±2 (energy)", 0.6
    return "key clash", 0.0
