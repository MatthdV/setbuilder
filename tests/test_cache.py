import sqlite3

from setbuilder.cache import open_cache

EXPECTED_COLUMNS = [
    "content_id",
    "title",
    "artist",
    "album",
    "bpm",
    "camelot",
    "rb_key",
    "moment",
    "ambiance",
    "genre",
    "file_path",
    "file_status",
    "duration_s",
    "has_cues",
    "has_phrases",
    "updated_at",
]


def test_open_cache_creates_schema(tmp_path):
    db_path = tmp_path / "setbuilder.db"

    conn = open_cache(str(db_path))

    assert isinstance(conn, sqlite3.Connection)
    rows = conn.execute("PRAGMA table_info(tracks)").fetchall()
    assert [row[1] for row in rows] == EXPECTED_COLUMNS
    pk_cols = [row[1] for row in rows if row[5]]
    assert pk_cols == ["content_id"]
    conn.close()
