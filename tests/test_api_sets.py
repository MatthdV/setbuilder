import sqlite3

from fastapi.testclient import TestClient

from setbuilder.api import create_app
from setbuilder.features_cache import open_features
from setbuilder.sets_repo import open_sets


def _make_db(path):
    c = sqlite3.connect(path)
    c.execute(
        """CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
           bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)"""
    )
    c.execute("CREATE TABLE galaxy (content_id TEXT PRIMARY KEY, umap_x REAL, umap_y REAL, umap_version TEXT)")
    open_features(c)
    open_sets(c)
    c.commit()
    c.close()


def _client(tmp_path):
    db = tmp_path / "setbuilder.db"
    _make_db(str(db))
    return TestClient(create_app(str(db)))


def test_set_crud_via_api(tmp_path):
    client = _client(tmp_path)
    r = client.post("/sets", json={"name": "Club", "mode": "count", "target": 3,
                                   "curve_points": [[0, 2], [1, 8]], "n_slots": 3})
    assert r.status_code == 200
    sid = r.json()["set_id"]

    rec = client.get(f"/sets/{sid}").json()
    assert len(rec["slots"]) == 3

    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a", "is_anchor": True})
    rec = client.get(f"/sets/{sid}").json()
    assert rec["slots"][0]["content_id"] == "a" and rec["slots"][0]["is_anchor"] is True

    client.delete(f"/sets/{sid}/slots/0")
    assert client.get(f"/sets/{sid}").json()["slots"][0]["content_id"] is None

    assert client.get("/sets/doesnotexist").status_code == 404


def test_library_and_galaxy_endpoints(tmp_path):
    client = _client(tmp_path)
    assert client.get("/library").json() == []
    assert client.get("/galaxy").json() == []


def test_app_self_initialises_set_tables(tmp_path):
    # base avec seulement `tracks` (pas d'open_sets/open_features) : l'app doit
    # créer les tables manquantes elle-même, sinon POST /sets casse.
    db = tmp_path / "bare.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT, "
              "bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)")
    c.commit()
    c.close()
    client = TestClient(create_app(str(db)))
    r = client.post("/sets", json={"name": "x", "mode": "count", "target": 2,
                                   "curve_points": [[0, 5]], "n_slots": 2})
    assert r.status_code == 200
    assert client.get("/galaxy").json() == []
