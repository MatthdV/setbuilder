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
CREATE TABLE IF NOT EXISTS analyze_failures (
    content_id       TEXT,
    analysis_version TEXT,
    error            TEXT,
    failed_at        TEXT,
    file_path        TEXT,
    PRIMARY KEY (content_id, analysis_version)
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


def _migrate(cache):
    cols = {r[1] for r in cache.execute("PRAGMA table_info(analyze_failures)")}
    if cols and "file_path" not in cols:
        cache.execute("ALTER TABLE analyze_failures ADD COLUMN file_path TEXT")


def open_features(cache: sqlite3.Connection) -> None:
    """Crée les tables features et galaxy si absentes."""
    cache.executescript(_SCHEMA)
    _migrate(cache)
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


def record_failure(cache: sqlite3.Connection, content_id: str, analysis_version: str, error: str,
                   file_path: str | None = None) -> None:
    """Mémorise un échec d'analyse (pas les fichiers introuvables : une clé USB peut revenir)."""
    cache.execute(
        "INSERT OR REPLACE INTO analyze_failures (content_id, analysis_version, error, failed_at, file_path) "
        "VALUES (?, ?, ?, ?, ?)",
        (content_id, analysis_version, error[:200],
         datetime.now(timezone.utc).isoformat(timespec="seconds"), file_path),
    )
    cache.commit()


def reset_failures(cache: sqlite3.Connection) -> int:
    """Retry délibéré : oublie tous les échecs mémorisés. Retourne le nombre effacé."""
    n = cache.execute("DELETE FROM analyze_failures").rowcount
    cache.commit()
    return n


# Énergie RELATIVE à la bibliothèque (energy-v2, calculée à la volée, sans ré-analyse).
# L'arousal seul (modèle DEAM) est un mauvais proxy « club » : très tassé (écart-type 0,07) et
# il classe la techno/trance sous la house. On le combine, en z-scores par version d'analyse :
#   0.35 arousal + 0.25 agressivité - 0.25 « relaxed » + 0.15 BPM
# puis rang percentile -> 1..10. Features/BPM manquants = neutre (z = 0). Repli sur
# energy_score absolu si l'arousal manque. Poids = constantes ci-dessous.
ENERGY_W = {"arousal": 0.35, "aggressive": 0.25, "relaxed": -0.25, "bpm": 0.15}


def _z(col: str) -> str:
    # z-score fenêtré par version ; écart-type 0 / valeur absente -> 0
    mean = f"AVG({col}) OVER w"
    sd = f"SQRT(MAX(AVG({col} * {col}) OVER w - {mean} * {mean}, 0))"
    return f"COALESCE(({col} - {mean}) / NULLIF({sd}, 0), 0)"


REL_ENERGY_CTE = (
    "WITH base AS (SELECT f.content_id, f.analysis_version, f.arousal AS a, "
    "f.mood_aggressive AS g, f.mood_relaxed AS l, t.bpm AS b "
    "FROM features f LEFT JOIN tracks t ON t.content_id = f.content_id WHERE f.arousal IS NOT NULL), "
    "sc AS (SELECT content_id, analysis_version, "
    f"{ENERGY_W['arousal']} * {_z('a')} + {ENERGY_W['aggressive']} * {_z('g')} "
    f"+ {ENERGY_W['relaxed']} * {_z('l')} + {ENERGY_W['bpm']} * {_z('b')} AS score "
    "FROM base WINDOW w AS (PARTITION BY analysis_version)), "
    "r AS (SELECT content_id, analysis_version, "
    "PERCENT_RANK() OVER (PARTITION BY analysis_version ORDER BY score) AS pr FROM sc) "
)
REL_ENERGY_JOIN = "LEFT JOIN r ON r.content_id = f.content_id AND r.analysis_version = f.analysis_version "
REL_ENERGY_SQL = "COALESCE(CAST(ROUND(1 + 9 * r.pr) AS INTEGER), f.energy_score)"
