import sqlite3

from setbuilder.candidates import load_candidates, rank
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.scoring import Candidate, SlotContext


def _db():
    c = sqlite3.connect(":memory:")
    c.execute(
        """CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
           bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT)"""
    )
    open_features(c)
    return c


def test_left_join_keeps_unanalysed_track():
    c = _db()
    c.execute("INSERT INTO tracks VALUES ('t1','A','x',128.0,'8A',NULL,NULL,'techno')")
    cands = load_candidates(c, "av1")
    assert len(cands) == 1 and cands[0].energy is None


def test_filter_by_genre():
    c = _db()
    c.execute("INSERT INTO tracks VALUES ('t1','A','x',128.0,'8A',NULL,NULL,'techno')")
    c.execute("INSERT INTO tracks VALUES ('t2','B','x',128.0,'8A',NULL,NULL,'house')")
    assert {x.content_id for x in load_candidates(c, "av1", genres=["techno"])} == {"t1"}


def test_rank_orders_and_excludes():
    c = _db()
    c.execute("INSERT INTO tracks VALUES ('good','G','x',128.0,'8A',NULL,NULL,'techno')")
    c.execute("INSERT INTO tracks VALUES ('bad','B','x',128.0,'3B',NULL,NULL,'techno')")
    c.execute("INSERT INTO tracks VALUES ('self','S','x',128.0,'8A',NULL,NULL,'techno')")
    for cid in ("good", "bad", "self"):
        upsert_features(c, cid, {"energy_score": 7, "analysis_version": "av1"})
    prev = Candidate(content_id="p", title=None, artist=None, bpm=128.0, camelot="8A",
                     energy=7, moment=None, ambiance=None, embedding=None)
    ranked = rank(load_candidates(c, "av1"), SlotContext(prev=prev, target_energy=7.0),
                  exclude_ids={"self"})
    assert [r.content_id for r in ranked] == ["good", "bad"]


def test_empty_after_filter_is_empty_list():
    c = _db()
    assert rank(load_candidates(c, "av1", genres=["house"]),
                SlotContext(prev=None, target_energy=5.0)) == []
