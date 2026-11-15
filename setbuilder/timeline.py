"""Mapping d'un slot vers sa position normalisée [0,1] sur la courbe d'énergie.

Deux modes de set (§4.4) :
- `count`  : axe = index de slot, N slots régulièrement espacés.
- `duration` : axe = temps, position = durée cumulée des morceaux en amont / cible.
Un slot vide ne compte aucune durée (il ne décale pas les suivants).
"""


def _dur(d: float | None) -> float:
    return float(d) if d else 0.0


def slot_position(
    index: int, n_slots: int, mode: str, durations: list[float | None], target: float
) -> float:
    """Position normalisée [0,1] du slot `index`."""
    if mode == "count":
        return index / (n_slots - 1) if n_slots > 1 else 0.0
    # mode durée : temps cumulé avant ce slot, rapporté à la cible
    elapsed = sum(_dur(d) for d in durations[:index])
    if target <= 0:
        return 0.0
    return max(0.0, min(1.0, elapsed / target))


def slot_start_times(durations: list[float | None]) -> list[float]:
    """Temps de départ de chaque slot (somme des durées des slots précédents)."""
    starts, acc = [], 0.0
    for d in durations:
        starts.append(acc)
        acc += _dur(d)
    return starts
