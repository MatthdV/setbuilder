"""Table de mixage par clé Camelot (« perfect / boost / drop / mood »).

Pour une clé de départ, chaque clé d'arrivée appartient à une catégorie :
- perfect : même clé + son partenaire de la table (A : n-1 en B ; B : n+1 en A)
- boost 1/2/3 : l'énergie monte (+, ++, +++)
- drop 1/2/3  : l'énergie baisse (-, --, ---)
- mood : changement d'ambiance
Les valeurs « entre parenthèses » de la table sont marquées `weak` (option plus risquée).
La table est générée par des règles (numéros modulo 12) et vérifiée par tests contre
la table de référence complète.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RE = re.compile(r"^(1[0-2]|[1-9])([AB])$")


@dataclass(frozen=True)
class Move:
    category: str  # perfect | boost | drop | mood
    tier: int      # 0 pour perfect/mood, 1..3 pour boost/drop
    weak: bool = False

    @property
    def label(self) -> str:
        if self.category == "perfect":
            return "key perfect"
        if self.category == "mood":
            return "key mood change"
        sign = "+" if self.category == "boost" else "-"
        return f"key {self.category} {sign * self.tier}" + (" (alt)" if self.weak else "")


def _n(x: int) -> int:
    return (x - 1) % 12 + 1


def _parse(code: str | None) -> tuple[int, str] | None:
    if not code:
        return None
    m = _RE.match(code.strip().upper())
    return (int(m.group(1)), m.group(2)) if m else None


def moves_from(code: str | None) -> dict[str, Move]:
    """{clé d'arrivée: Move} depuis `code` ; {} si la clé n'est pas Camelot."""
    p = _parse(code)
    if p is None:
        return {}
    n, L = p
    out: dict[str, Move] = {}

    def add(num: int, letter: str, move: Move) -> None:
        out.setdefault(f"{_n(num)}{letter}", move)

    other = "B" if L == "A" else "A"
    if L == "A":
        add(n, "A", Move("perfect", 0)); add(n - 1, "B", Move("perfect", 0))
        add(n, "B", Move("boost", 1)); add(n + 1, "A", Move("boost", 1))
        add(n + 9, "A", Move("boost", 2))
        add(n + 2, "A", Move("boost", 3)); add(n + 7, "A", Move("boost", 3, True))
        add(n - 1, "A", Move("drop", 1))
        add(n + 3, "A", Move("drop", 2))
        add(n - 2, "A", Move("drop", 3)); add(n + 5, "A", Move("drop", 3, True))
        add(n + 3, "B", Move("mood", 0))
    else:
        add(n, "B", Move("perfect", 0)); add(n + 1, "A", Move("perfect", 0))
        add(n + 1, "B", Move("boost", 1))
        add(n + 9, "B", Move("boost", 2))
        add(n + 2, "B", Move("boost", 3)); add(n + 7, "B", Move("boost", 3, True))
        add(n, "A", Move("drop", 1)); add(n - 1, "B", Move("drop", 1))
        add(n + 3, "B", Move("drop", 2))
        add(n - 2, "B", Move("drop", 3)); add(n + 5, "B", Move("drop", 3, True))
        add(n + 9, "A", Move("mood", 0))
    _ = other
    return out


def key_move(prev: str | None, cand: str | None) -> Move | None:
    c = _parse(cand)
    if c is None:
        return None
    return moves_from(prev).get(f"{c[0]}{c[1]}")


# Sous-score de base par catégorie/tier ; modulé par le sens voulu pour l'énergie.
_BASE = {("boost", 1): 0.92, ("boost", 2): 0.84, ("boost", 3): 0.74,
         ("drop", 1): 0.92, ("drop", 2): 0.84, ("drop", 3): 0.74}


def move_score(move: Move, energy_delta: float | None) -> float:
    """0..1. `energy_delta` = énergie cible du slot - énergie du morceau précédent
    (None si inconnue) : un boost est favorisé quand il faut monter, un drop quand il faut
    descendre, et pénalisé dans le sens inverse."""
    if move.category == "perfect":
        return 0.9
    if move.category == "mood":
        return 0.55
    base = _BASE[(move.category, move.tier)] * (0.85 if move.weak else 1.0)
    if energy_delta is None or abs(energy_delta) < 0.75:
        return base * 0.85  # pas de direction nette : utile mais pas prioritaire
    wants_up = energy_delta > 0
    aligned = (move.category == "boost") == wants_up
    return base * (1.05 if aligned else 0.6)
