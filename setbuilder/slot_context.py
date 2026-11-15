"""Construction du contexte de scoring d'un slot : morceau précédent réel +
cible d'énergie lue sur la courbe à la position du slot.
"""

import sqlite3

from setbuilder.candidates import load_candidates
from setbuilder.curve import EnergyCurve
from setbuilder.scoring import Candidate, SlotContext
from setbuilder.sets_repo import SetRecord
from setbuilder.timeline import slot_position


def candidates_by_id(cache: sqlite3.Connection, analysis_version: str) -> dict[str, Candidate]:
    """Indexe tous les candidats de la lib par content_id."""
    return {c.content_id: c for c in load_candidates(cache, analysis_version)}


def build_slot_context(
    set_rec: SetRecord,
    slot_index: int,
    by_id: dict[str, Candidate],
    durations: list[float | None],
) -> SlotContext:
    """`prev` = dernier slot rempli (et connu du cache) avant `slot_index` ;
    `target_energy` = courbe à la position normalisée du slot."""
    prev: Candidate | None = None
    for i in range(slot_index - 1, -1, -1):
        cid = set_rec.slots[i].content_id
        if cid and cid in by_id:
            prev = by_id[cid]
            break
    curve = EnergyCurve.from_points(set_rec.curve_points)
    pos = slot_position(slot_index, len(set_rec.slots), set_rec.mode, durations, set_rec.target)
    return SlotContext(prev=prev, target_energy=curve.target_at(pos))
