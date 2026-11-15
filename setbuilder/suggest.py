"""Suggestions classées pour un slot : câble le moteur de scoring (plan 3) au
contexte du slot (morceau précédent + cible d'énergie), en excluant les
morceaux déjà posés dans le set.
"""

import sqlite3

from setbuilder.candidates import load_candidates, rank
from setbuilder.scoring import DEFAULT_WEIGHTS, ScoreBreakdown, Weights
from setbuilder.sets_repo import SetRecord
from setbuilder.slot_context import build_slot_context, candidates_by_id


def _durations_per_slot(cache: sqlite3.Connection, set_rec: SetRecord) -> list[float | None]:
    rows = cache.execute("SELECT content_id, duration_s FROM tracks").fetchall()
    by_id = {cid: dur for cid, dur in rows}
    return [by_id.get(s.content_id) if s.content_id else None for s in set_rec.slots]


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
    return ranked[:limit]
