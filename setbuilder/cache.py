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


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """Pose les pragmas de concurrence sur une connexion du cache.

    Serveur web et sous-process d'analyse partagent setbuilder.db. Ordre
    volontaire : busy_timeout AVANT journal_mode=WAL, pour que le passage en
    WAL lui-même attende si la base est brièvement verrouillée. WAL = lecteurs
    ne bloquent pas l'écrivain ; synchronous=NORMAL = durabilité suffisante en
    WAL avec de meilleures perfs.
    """
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")


def open_cache(path: str) -> sqlite3.Connection:
    """Ouvre (ou crée) le cache et garantit que le schéma existe."""
    conn = sqlite3.connect(path)
    apply_pragmas(conn)
    conn.execute(_SCHEMA)
    conn.commit()
    return conn
