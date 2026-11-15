"""Smoke e2e : assets web servis + scenario API complet (create -> ancre ->
suggestions -> force -> export via fake provider)."""
import sqlite3

import numpy as np
from fastapi.testclient import TestClient

from setbuilder.api import create_app
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.sets_repo import open_sets

WEB_ASSETS = ["tokens.css", "app.css", "app.js", "curve.js", "timeline.js",
              "suggestions.js", "galaxy.js"]


class _FakeRB:
    def __init__(self):
        self.added = []

    def create_playlist(self, name, **kw):
        return {"name": name}

    def add_to_playlist(self, pl, cid):
        self.added.append(cid)

    def commit(self):
        pass


def _realistic_db(path):
    c = sqlite3.connect(path)
    c.execute(
        """CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
           bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT, duration_s REAL)"""
    )
    c.execute("CREATE TABLE galaxy (content_id TEXT PRIMARY KEY, umap_x REAL, umap_y REAL, umap_version TEXT)")
    open_features(c)
    open_sets(c)
    rng = np.random.default_rng(3)
    for i in range(10):
        cid = f"s{i:02d}"
        c.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?)",
                  (cid, f"T{i}", "Artist", 124.0 + i, "8A", None, None, "Techno", 360.0))
        upsert_features(c, cid, {"energy_score": 5, "top_genre": "Techno",
                                 "muq_embedding": rng.standard_normal(1024).astype("float32"),
                                 "analysis_version": "av1"})
        c.execute("INSERT INTO galaxy VALUES (?,?,?,?)",
                  (cid, float(rng.standard_normal()), float(rng.standard_normal()), "v1"))
    c.commit()
    c.close()


def _client(tmp_path, fake):
    db = tmp_path / "setbuilder.db"
    _realistic_db(str(db))
    rbdir = tmp_path / "rb"
    rbdir.mkdir()
    (rbdir / "master.db").write_text("DB")
    return TestClient(create_app(str(db), rb_provider=lambda: (fake, str(rbdir))))


def test_index_and_assets_served(tmp_path):
    client = _client(tmp_path, _FakeRB())
    html = client.get("/").text
    assert "/static/app.js" in html and "/static/tokens.css" in html
    for a in WEB_ASSETS:
        assert client.get("/static/" + a).status_code == 200, a


def test_full_api_scenario_through_export(tmp_path):
    fake = _FakeRB()
    client = _client(tmp_path, fake)

    # library + galaxy peuples
    assert len(client.get("/library").json()) == 10
    assert len(client.get("/galaxy").json()) == 10

    sid = client.post("/sets", json={"name": "Smoke", "mode": "count", "target": 4,
                                     "curve_points": [[0, 2], [0.5, 9], [1, 4]],
                                     "n_slots": 4}).json()["set_id"]

    # ancre slot 0
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "s00", "is_anchor": True})

    # suggestions pour slot 1 : classees, non vides
    sugg = client.get(f"/sets/{sid}/slots/1/suggestions?limit=5").json()
    assert sugg and sugg[0]["content_id"] != "s00"
    assert [s["score"] for s in sugg] == sorted((s["score"] for s in sugg), reverse=True)

    # force slot 2 : renvoie un impact
    forced = client.post(f"/sets/{sid}/slots/2/force", json={"content_id": "s07"})
    assert forced.status_code == 200
    assert "impact" in forced.json()

    # export : 2 slots remplis (0, 2) dans l'ordre + backup
    r = client.post(f"/sets/{sid}/export")
    assert r.status_code == 200
    body = r.json()
    assert body["n_tracks"] == 2
    assert body["playlist"] == "Smoke"
    assert "backup" in body
    assert fake.added == ["s00", "s07"]
