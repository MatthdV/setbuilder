import sqlite3

from fastapi.testclient import TestClient

from setbuilder.api import create_app
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.sets_repo import open_sets


def _client(tmp_path):
    db = tmp_path / "setbuilder.db"
    c = sqlite3.connect(str(db))
    c.execute(
        """CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
           bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)"""
    )
    c.execute("CREATE TABLE galaxy (content_id TEXT PRIMARY KEY, umap_x REAL, umap_y REAL, umap_version TEXT)")
    open_features(c)
    open_sets(c)
    for cid, bpm, cam, en in [("a", 128.0, "8A", 7), ("good", 128.0, "8A", 7), ("clash", 150.0, "3B", 2)]:
        c.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?)",
                  (cid, cid, "x", bpm, cam, None, None, "techno", 200.0))
        upsert_features(c, cid, {"energy_score": en, "analysis_version": "av1"})
    c.commit()
    c.close()
    return TestClient(create_app(str(db)))


def _make_set(client):
    return client.post("/sets", json={"name": "x", "mode": "count", "target": 3,
                                      "curve_points": [[0, 7], [1, 7]], "n_slots": 3}).json()["set_id"]


def test_suggestions_and_force_impact(tmp_path):
    client = _client(tmp_path)
    sid = _make_set(client)
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a", "is_anchor": True})

    sugg = client.get(f"/sets/{sid}/slots/1/suggestions?limit=5").json()
    assert isinstance(sugg, list) and sugg
    for s in sugg:
        assert set(s["dimensions"]) == {"key", "bpm", "energy", "vibe", "ambiance"}
    assert all(s["content_id"] != "a" for s in sugg)

    r = client.post(f"/sets/{sid}/slots/1/force", json={"content_id": "clash"})
    assert r.status_code == 200
    body = r.json()
    assert "impact" in body and "warnings" in body["impact"]
    assert body["impact"]["warnings"]  # clash + énergie
    assert client.get(f"/sets/{sid}").json()["slots"][1]["is_forced"] is True


def test_force_unknown_track_404(tmp_path):
    client = _client(tmp_path)
    sid = _make_set(client)
    assert client.post(f"/sets/{sid}/slots/0/force", json={"content_id": "ghost"}).status_code == 404
