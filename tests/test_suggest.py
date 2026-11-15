import sqlite3

from setbuilder.features_cache import open_features, upsert_features
from setbuilder.sets_repo import create_set, open_sets, place_track, get_set
from setbuilder.suggest import suggestions_for_slot


def _db():
    c = sqlite3.connect(":memory:")
    c.execute(
        """CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
           bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)"""
    )
    open_features(c)
    open_sets(c)
    return c


def _seed(c):
    rows = [("a", 128.0, "8A", 7), ("good", 128.0, "8A", 7), ("bad", 150.0, "3B", 2)]
    for cid, bpm, cam, en in rows:
        c.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?)",
                  (cid, cid, "x", bpm, cam, None, None, "techno", 200.0))
        upsert_features(c, cid, {"energy_score": en, "analysis_version": "av1"})


def test_suggestions_exclude_placed_and_limit():
    c = _db()
    _seed(c)
    sid = create_set(c, "x", "count", 3, [(0.0, 7.0), (1.0, 7.0)], "av1", n_slots=3)
    place_track(c, sid, 0, "a", is_anchor=True)
    rec = get_set(c, sid)
    sugg = suggestions_for_slot(c, rec, 1, limit=2)
    assert all(s.content_id != "a" for s in sugg)
    assert len(sugg) <= 2
    assert [s.score for s in sugg] == sorted([s.score for s in sugg], reverse=True)
    assert sugg[0].content_id == "good"  # compatible devant le clash


def test_suggestions_empty_library():
    c = _db()
    sid = create_set(c, "x", "count", 2, [(0.0, 5.0)], "av1", n_slots=2)
    assert suggestions_for_slot(c, get_set(c, sid), 0) == []
