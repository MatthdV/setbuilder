"""Chargement des candidats depuis le cache local et classement par slot.

Seul point d'I/O du moteur de scoring. Jointure LEFT : un morceau non encore
analysé reste candidat (dimensions ML neutres), jamais exclu silencieusement.
"""

import sqlite3

import numpy as np

from setbuilder.features_cache import REL_ENERGY_CTE, REL_ENERGY_JOIN, REL_ENERGY_SQL

from setbuilder.scoring import (
    DEFAULT_WEIGHTS,
    Candidate,
    ScoreBreakdown,
    SlotContext,
    Weights,
    score_candidate,
)


def _decode_embedding(blob: bytes | None, dim: int | None) -> np.ndarray | None:
    if not blob or not dim:
        return None
    return np.frombuffer(blob, dtype=np.float32, count=dim).copy()


def load_candidates(
    cache: sqlite3.Connection,
    analysis_version: str,
    *,
    genres: list[str] | None = None,
    moments: list[str] | None = None,
) -> list[Candidate]:
    """Candidats = tracks ⨝ features (LEFT, à `analysis_version`), filtres optionnels."""
    sql = [
        REL_ENERGY_CTE +
        "SELECT t.content_id, t.title, t.artist, t.bpm, t.camelot, t.moment, t.ambiance, "
        f"{REL_ENERGY_SQL}, f.muq_embedding, f.muq_dim "
        "FROM tracks t "
        "LEFT JOIN features f ON f.content_id = t.content_id AND f.analysis_version = ? "
        + REL_ENERGY_JOIN
    ]
    params: list = [analysis_version]
    where = []
    if genres:
        where.append(f"t.genre IN ({', '.join('?' for _ in genres)})")
        params += genres
    if moments:
        where.append(f"t.moment IN ({', '.join('?' for _ in moments)})")
        params += moments
    if where:
        sql.append("WHERE " + " AND ".join(where))
    rows = cache.execute(" ".join(sql), params).fetchall()
    out = []
    for cid, title, artist, bpm, camelot, moment, ambiance, energy, emb, dim in rows:
        out.append(Candidate(
            content_id=cid, title=title, artist=artist, bpm=bpm, camelot=camelot,
            energy=energy, moment=moment, ambiance=ambiance,
            embedding=_decode_embedding(emb, dim),
        ))
    return out


def rank(
    candidates: list[Candidate],
    ctx: SlotContext,
    weights: Weights = DEFAULT_WEIGHTS,
    *,
    exclude_ids: set[str] | None = None,
) -> list[ScoreBreakdown]:
    """Classement par score décroissant (tie-break stable par content_id).

    `exclude_ids` retire les morceaux déjà posés dans le set.
    """
    excluded = exclude_ids or set()
    scored = [
        score_candidate(c, ctx, weights) for c in candidates if c.content_id not in excluded
    ]
    scored.sort(key=lambda b: (-b.score, b.content_id))
    return scored
