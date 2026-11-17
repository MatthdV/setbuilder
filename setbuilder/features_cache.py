"""Tables de features (Essentia + MuQ) et de carte UMAP, dans le cache local.

Jamais de master.db ici : tout vit dans setbuilder.db.
"""

import sqlite3
from datetime import datetime, timezone

import numpy as np

_SCHEMA = """
CREATE TABLE IF NOT EXISTS features (
    content_id      TEXT PRIMARY KEY,
    top_genre       TEXT,
    genres_json     TEXT,
    mood_happy      REAL,
    mood_sad        REAL,
    mood_party      REAL,
    mood_relaxed    REAL,
    mood_aggressive REAL,
    valence         REAL,
    arousal         REAL,
    energy_score    INTEGER,
    muq_embedding   BLOB,
    muq_dim         INTEGER,
    analysis_version TEXT,
    analyzed_at     TEXT
);
CREATE TABLE IF NOT EXISTS galaxy (
    content_id   TEXT PRIMARY KEY,
    umap_x       REAL,
    umap_y       REAL,
    umap_version TEXT
);
"""

_COLUMNS = {
    "top_genre", "genres_json", "mood_happy", "mood_sad", "mood_party", "mood_relaxed",
    "mood_aggressive", "valence", "arousal", "energy_score", "muq_embedding", "muq_dim",
    "analysis_version", "analyzed_at",
}


def open_features(cache: sqlite3.Connection) -> None:
    """Crée les tables features et galaxy si absentes."""
    cache.executescript(_SCHEMA)
    cache.commit()


def upsert_features(cache: sqlite3.Connection, content_id: str, feats: dict) -> None:
    """Insère ou met à jour les colonnes fournies (les autres restent inchangées).

    `muq_embedding` peut être un ndarray : il est stocké en float32 (BLOB) et
    `muq_dim` est renseigné. `analyzed_at` est posé automatiquement si absent.
    """
    values = dict(feats)
    emb = values.get("muq_embedding")
    if emb is not None and not isinstance(emb, (bytes, bytearray)):
        arr = np.asarray(emb, dtype=np.float32)
        values["muq_embedding"] = arr.tobytes()
        values["muq_dim"] = int(arr.shape[-1])
    values.setdefault("analyzed_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    unknown = set(values) - _COLUMNS
    if unknown:
        raise ValueError(f"colonnes de features inconnues : {sorted(unknown)}")

    cols = ["content_id", *values]
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in values)
    cache.execute(
        f"INSERT INTO features ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(content_id) DO UPDATE SET {updates}",
        [content_id, *values.values()],
    )
    cache.commit()


def has_features(cache: sqlite3.Connection, content_id: str, analysis_version: str) -> bool:
    row = cache.execute(
        "SELECT 1 FROM features WHERE content_id = ? AND analysis_version = ?",
        (content_id, analysis_version),
    ).fetchone()
    return row is not None


def resolve_analysis_version(cache: sqlite3.Connection, stored: str) -> str:
    """`stored` s'il a des features ; sinon la version la plus fournie (sets legacy)."""
    if cache.execute("SELECT 1 FROM features WHERE analysis_version = ? LIMIT 1", (stored,)).fetchone():
        return stored
    row = cache.execute("SELECT analysis_version FROM features WHERE analysis_version IS NOT NULL "
                        "GROUP BY analysis_version ORDER BY COUNT(*) DESC LIMIT 1").fetchone()
    return row[0] if row else stored
