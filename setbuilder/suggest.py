"""Suggestions classées pour un slot : câble le moteur de scoring (plan 3) au
contexte du slot (morceau précédent + cible d'énergie), en excluant les
morceaux déjà posés dans le set.
"""

import sqlite3

from setbuilder.candidates import load_candidates, rank
from setbuilder.scoring import DEFAULT_WEIGHTS, ScoreBreakdown, Weights
from setbuilder.sets_repo import SetRecord
from setbuilder.keymoves import key_move, moves_from
from setbuilder.slot_context import build_slot_context, candidates_by_id


def _durations_per_slot(cache: sqlite3.Connection, set_rec: SetRecord) -> list[float | None]:
    rows = cache.execute("SELECT content_id, duration_s FROM tracks").fetchall()
    by_id = {cid: dur for cid, dur in rows}
    return [by_id.get(s.content_id) if s.content_id else None for s in set_rec.slots]


def _quotas(delta: float | None) -> dict[str, int]:
    """Part de chaque famille de clés dans la liste (sur ~15), selon le sens d'énergie voulu."""
    if delta is not None and delta >= 0.75:
        return {"perfect": 4, "boost": 6, "drop": 1, "mood": 2, "other": 2}
    if delta is not None and delta <= -0.75:
        return {"perfect": 4, "boost": 1, "drop": 6, "mood": 2, "other": 2}
    return {"perfect": 6, "boost": 3, "drop": 3, "mood": 2, "other": 1}


def diversify(ranked: list[ScoreBreakdown], prev, by_id, delta, limit: int) -> list[ScoreBreakdown]:
    """Évite une liste 100 % « même clé » : garantit des quotas par famille de clé
    (perfect / boost / drop / mood), complétés par le meilleur score restant."""
    if limit <= 0:
        return []
    if prev is None or not moves_from(prev.camelot):  # pas de clé Camelot valide : classement brut
        return ranked[:limit]

    def family(b: ScoreBreakdown) -> str:
        cand = by_id.get(b.content_id)
        if cand is None or cand.camelot is None:
            return "skip"  # clé inconnue : seulement en complément, pas dans un quota
        m = key_move(prev.camelot, cand.camelot)
        if m is not None and m.category == "perfect" and cand.camelot.strip().upper() == prev.camelot.strip().upper():
            return "perfect"
        if m:
            return m.category
        return "skip" if b.dimensions["key"][1] <= 0.0 else "other"  # clash : jamais un « quota »

    quotas = _quotas(delta)
    scale = limit / 15
    taken: list[ScoreBreakdown] = []
    used: set[str] = set()
    counts = {k: 0 for k in quotas}
    per_key: dict[str | None, int] = {}
    key_cap = max(1, round(3 * scale))  # varier les clés à l'intérieur d'une famille
    for b in ranked:
        f = family(b)
        if f == "skip":
            continue
        k = by_id[b.content_id].camelot
        if counts[f] < max(1, round(quotas[f] * scale)) and (f == "perfect" or per_key.get(k, 0) < key_cap):
            taken.append(b); used.add(b.content_id); counts[f] += 1; per_key[k] = per_key.get(k, 0) + 1
            if len(taken) >= limit:
                break
    for b in ranked:  # complète avec les meilleurs restants
        if len(taken) >= limit:
            break
        if b.content_id not in used:
            taken.append(b); used.add(b.content_id)
    taken.sort(key=lambda b: (-b.score, b.content_id))
    return taken


def suggestions_for_slot(
    cache: sqlite3.Connection,
    set_rec: SetRecord,
    slot_index: int,
    *,
    weights: Weights = DEFAULT_WEIGHTS,
    limit: int = 20,
) -> list[ScoreBreakdown]:
    by_id = candidates_by_id(cache, set_rec.analysis_version)
    durations = _durations_per_slot(cache, set_rec)
    ctx = build_slot_context(set_rec, slot_index, by_id, durations)
    placed = {s.content_id for s in set_rec.slots if s.content_id}
    ranked = rank(load_candidates(cache, set_rec.analysis_version), ctx, weights, exclude_ids=placed)
    delta = None if ctx.prev is None or ctx.prev.energy is None else ctx.target_energy - ctx.prev.energy
    return diversify(ranked, ctx.prev, by_id, delta, limit)
