import sqlite3

from fastapi.testclient import TestClient

from setbuilder.analyze import ANALYSIS_VERSION
from setbuilder.api import create_app
from setbuilder.candidates import load_candidates
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.sets_repo import open_sets


def _db(tmp_path, with_arousal=True):
    path = str(tmp_path / "s.db")
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT, bpm REAL,
                 camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)""")
    open_features(c); open_sets(c)
    for i in range(11):  # arousal 0.50..0.60 : énergie absolue tassée sur 7, relative étalée
        c.execute("INSERT INTO tracks (content_id, title) VALUES (?, ?)", (f"t{i}", f"t{i}"))
        feats = {"energy_score": 7, "analysis_version": ANALYSIS_VERSION}
        if with_arousal:
            feats["arousal"] = 0.50 + i * 0.01
        upsert_features(c, f"t{i}", feats)
    c.commit()
    return path, c


def test_library_energy_is_relative_and_spread(tmp_path):
    path, _ = _db(tmp_path)
    rows = TestClient(create_app(path)).get("/library").json()
    by = {r["content_id"]: r for r in rows}
    assert {r["energy_score"] for r in rows} == {7}          # absolu inchangé
    assert by["t0"]["energy"] == 1 and by["t10"]["energy"] == 10
    assert by["t0"]["energy"] < by["t5"]["energy"] < by["t10"]["energy"]


def test_candidates_use_relative_energy(tmp_path):
    _, c = _db(tmp_path)
    e = {x.content_id: x.energy for x in load_candidates(c, ANALYSIS_VERSION)}
    assert e["t0"] == 1 and e["t10"] == 10


def test_falls_back_to_absolute_without_arousal(tmp_path):
    path, _ = _db(tmp_path, with_arousal=False)
    rows = TestClient(create_app(path)).get("/library").json()
    assert {r["energy"] for r in rows} == {7}


def test_composite_ranks_aggressive_fast_above_relaxed_slow(tmp_path):
    path = str(tmp_path / "c.db")
    c = sqlite3.connect(path)
    c.execute("""CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT, bpm REAL,
                 camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)""")
    open_features(c); open_sets(c)
    spec = {  # même arousal : seuls agressivité / relaxed / BPM distinguent les morceaux
        "peak": (0.6, 0.8, 0.05, 135), "mid": (0.6, 0.3, 0.3, 128),
        "chill": (0.6, 0.05, 0.9, 118), "mid2": (0.6, 0.35, 0.25, 126),
    }
    for cid, (ar, ag, rl, bpm) in spec.items():
        c.execute("INSERT INTO tracks (content_id, title, bpm) VALUES (?, ?, ?)", (cid, cid, bpm))
        upsert_features(c, cid, {"arousal": ar, "mood_aggressive": ag, "mood_relaxed": rl,
                                 "energy_score": 7, "analysis_version": ANALYSIS_VERSION})
    c.commit()
    by = {r["content_id"]: r["energy"] for r in TestClient(create_app(path)).get("/library").json()}
    assert by["peak"] > by["mid2"] >= by["mid"] > by["chill"]
    assert by["peak"] == 10 and by["chill"] == 1
