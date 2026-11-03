from dataclasses import replace

from setbuilder.cache import open_cache
from setbuilder.rbread import Track
from setbuilder.sync import SyncStats, sync


def _track(cid, path, bpm=128.0):
    return Track(
        content_id=cid, title=f"T{cid}", artist="A", album=None, bpm=bpm,
        camelot="5A", rb_key="Cm", moment="Peak", ambiance="Dark", genre="House",
        file_path=path, duration_s=300, has_cues=1, has_phrases=0,
    )


def _setup(tmp_path):
    real = tmp_path / "a.mp3"
    real.write_bytes(b"x")
    tracks = [_track("1", str(real)), _track("2", str(tmp_path / "nope.mp3"))]
    return open_cache(str(tmp_path / "cache.db")), tracks


def test_sync_inserts_then_idempotent(tmp_path):
    cache, tracks = _setup(tmp_path)
    stats = sync(tracks, cache)
    assert stats == SyncStats(inserted=2, updated=0, missing_files=1)
    assert cache.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 2
    statuses = dict(cache.execute("SELECT content_id, file_status FROM tracks"))
    assert statuses == {"1": "ok", "2": "missing"}

    stats = sync(tracks, cache)
    assert stats == SyncStats(inserted=0, updated=0, missing_files=1)
    assert cache.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 2


def test_sync_updates_changed_field(tmp_path):
    cache, tracks = _setup(tmp_path)
    sync(tracks, cache)
    changed = [replace(tracks[0], bpm=130.0), tracks[1]]
    stats = sync(changed, cache)
    assert stats == SyncStats(inserted=0, updated=1, missing_files=1)
    bpm = cache.execute("SELECT bpm FROM tracks WHERE content_id='1'").fetchone()[0]
    assert bpm == 130.0


def test_sync_missing_file_keeps_original_path(tmp_path):
    cache, tracks = _setup(tmp_path)
    sync(tracks, cache)
    row = cache.execute(
        "SELECT file_path, file_status FROM tracks WHERE content_id='2'"
    ).fetchone()
    assert row == (str(tmp_path / "nope.mp3"), "missing")
