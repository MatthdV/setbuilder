"""Cache SQLite local de la librairie Rekordbox.

Fichier séparé de master.db : ce module ne touche jamais à Rekordbox.
"""

import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    content_id   TEXT PRIMARY KEY,
    title        TEXT,
    artist       TEXT,
    album        TEXT,
    bpm          REAL,
    camelot      TEXT,
    rb_key       TEXT,
    moment       TEXT,
    ambiance     TEXT,
    genre        TEXT,
    file_path    TEXT,
    file_status  TEXT,
    duration_s   REAL,
    has_cues     INT,
    has_phrases  INT,
    updated_at   TEXT
)
"""


def open_cache(path: str) -> sqlite3.Connection:
    """Ouvre (ou crée) le cache et garantit que le schéma existe."""
    conn = sqlite3.connect(path)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn
