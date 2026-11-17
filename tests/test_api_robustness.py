"""Régressions trouvées par le test bout-en-bout (validation, version d'analyse,
DB vide, export sans config Rekordbox)."""
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from setbuilder.analyze import ANALYSIS_VERSION
from setbuilder.api import _default_rb_provider, create_app
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.sets_repo import open_sets

GOOD = {"name": "x", "mode": "count", "target": 3,
        "curve_points": [[0, 2], [1, 8]], "n_slots": 3}


def _db(tmp_path, version=ANALYSIS_VERSION):
    db = tmp_path / "setbuilder.db"
    c = sqlite3.connect(str(db))
    c.execute(
        """CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
           bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)"""
    )
    c.execute("CREATE TABLE galaxy (content_id TEXT PRIMARY KEY, umap_x REAL, umap_y REAL, umap_version TEXT)")
    open_features(c)
    open_sets(c)
    for cid, bpm, cam, en in [("a", 128.0, "8A", 7), ("b", 128.0, "8A", 7), ("c", 150.0, "3B", 2)]:
        c.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?)",
                  (cid, cid, "x", bpm, cam, None, None, "techno", 200.0))
        upsert_features(c, cid, {"energy_score": en, "analysis_version": version})
    c.commit()
    c.close()
    return str(db)


def _client(tmp_path, **kw):
    return TestClient(create_app(_db(tmp_path, **kw)), raise_server_exceptions=False)


def _mk(client, **over):
    body = {**GOOD, **over}
    return client.post("/sets", json=body)


# --- B1 : version d'analyse ---------------------------------------------------

def test_new_set_defaults_to_current_analysis_version(tmp_path):
    client = _client(tmp_path)
    sid = _mk(client).json()["set_id"]
    assert client.get(f"/sets/{sid}").json()["analysis_version"] == ANALYSIS_VERSION


def test_legacy_av1_set_still_scores_energy(tmp_path):
    client = _client(tmp_path)  # features à la version courante
    sid = _mk(client, analysis_version="av1").json()["set_id"]
    sugg = client.get(f"/sets/{sid}/slots/0/suggestions").json()
    assert sugg and sugg[0]["dimensions"]["energy"][0] != "énergie n/a"


# --- B2 : validation de POST /sets --------------------------------------------

@pytest.mark.parametrize("over", [
    {"n_slots": 0}, {"n_slots": -1}, {"n_slots": 201},
    {"curve_points": []}, {"curve_points": [[0, 11]]}, {"curve_points": [[0, -1]]},
    {"curve_points": [[1.5, 5]]}, {"curve_points": [[-0.1, 5]]},
    {"target": 0}, {"target": -5},
    {"name": ""}, {"name": "   "}, {"name": "x" * 121},
    {"mode": "bogus"},
])
def test_create_set_rejects_invalid(tmp_path, over):
    assert _mk(_client(tmp_path), **over).status_code == 422


def test_create_set_rejects_nan(tmp_path):
    client = _client(tmp_path)
    raw = '{"name":"x","mode":"count","target":NaN,"curve_points":[[0,5]],"n_slots":3}'
    r = client.post("/sets", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_create_set_accepts_accents_emoji_and_strips(tmp_path):
    client = _client(tmp_path)
    r = _mk(client, name="  Été 🎧  ")
    assert r.status_code == 200
    assert client.get(f"/sets/{r.json()['set_id']}").json()["name"] == "Été 🎧"


def test_unsorted_curve_ok(tmp_path):
    assert _mk(_client(tmp_path), curve_points=[[1, 8], [0, 2]]).status_code == 200


def test_list_sets_skips_corrupt_row(tmp_path):
    path = _db(tmp_path)
    client = TestClient(create_app(path), raise_server_exceptions=False)
    ok = _mk(client).json()["set_id"]
    c = sqlite3.connect(path)
    c.execute("INSERT INTO sets VALUES ('bad','b','count',3,?, 'av1','2026-01-01')",
              ('[[0, NaN]]',))
    c.execute("INSERT INTO set_slots (set_id, position) VALUES ('bad', 0)")
    c.commit()
    c.close()
    r = client.get("/sets")
    assert r.status_code == 200
    assert [s["set_id"] for s in r.json()] == [ok]


# --- B4 / B5 -------------------------------------------------------------------

def test_put_slot_unknown_track_404(tmp_path):
    client = _client(tmp_path)
    sid = _mk(client).json()["set_id"]
    assert client.put(f"/sets/{sid}/slots/0", json={"content_id": "ZZZ"}).status_code == 404
    assert client.get(f"/sets/{sid}").json()["slots"][0]["content_id"] is None


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_suggestions_limit_bounds(tmp_path, limit):
    client = _client(tmp_path)
    sid = _mk(client).json()["set_id"]
    assert client.get(f"/sets/{sid}/slots/0/suggestions", params={"limit": limit}).status_code == 422


# --- B6 : export, config Rekordbox absente ---------------------------------------

def test_default_rb_provider_falls_back_when_config_missing(monkeypatch):
    import pyrekordbox.config as cfg

    def boom(*a, **k):
        raise KeyError("db_dir")

    monkeypatch.setattr(cfg, "get_config", boom)
    db_dir, open_db = _default_rb_provider()  # ne doit pas lever ; n'ouvre rien
    assert db_dir.endswith("Pioneer/rekordbox")
    assert callable(open_db)


# --- B7 : DB vide ---------------------------------------------------------------

def test_empty_db_endpoints_do_not_500(tmp_path):
    client = TestClient(create_app(str(tmp_path / "new.db")), raise_server_exceptions=False)
    assert client.get("/library").json() == []
    assert client.get("/galaxy").json() == []
    assert client.get("/analyze/pending").json() == {"pending": 0, "total": 0}


# --- sécurité locale : pas de CORS, pas de requête cross-origin -------------------

def test_cross_origin_requests_rejected(tmp_path):
    client = _client(tmp_path)
    r = client.post("/analyze", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert client.get("/library", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/library", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/library", headers={"Host": "[attacker.example]"}).status_code == 403
    assert client.get("/library", headers={"Host": "[::1]:8000"}).status_code == 200
    assert "access-control-allow-origin" not in client.get("/library").headers
    assert client.get("/library", headers={"Origin": "http://127.0.0.1:8000"}).status_code == 200
