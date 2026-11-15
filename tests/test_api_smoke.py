"""Smoke API bout-en-bout : db réaliste -> création set -> ancre -> suggestions
-> forçage avec impact -> relecture cohérente."""
import sqlite3

import numpy as np
from fastapi.testclient import TestClient

from setbuilder.api import create_app
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.sets_repo import open_sets

_DIM = 1024


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
    rng = np.random.default_rng(0)
    specs = [
        ("anchor", 128.0, "8A", 6), ("near", 129.0, "8A", 6), ("relative", 128.0, "8B", 7),
        ("clash", 150.0, "3B", 2), ("slow", 90.0, "6B", 9), ("mid", 131.0, "9A", 5),
    ]
    for i, (cid, bpm, cam, en) in enumerate(specs):
        c.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?)",
                  (cid, cid, "x", bpm, cam, None, None, "techno", 240.0))
        upsert_features(c, cid, {
            "energy_score": en,
            "muq_embedding": rng.standard_normal(_DIM).astype(np.float32),
            "analysis_version": "av1",
        })
        c.execute("INSERT INTO galaxy VALUES (?,?,?,?)", (cid, float(i), float(-i), "umap-v1"))
    c.commit()
    c.close()
    return TestClient(create_app(str(db)))


def test_end_to_end_api(tmp_path):
    client = _client(tmp_path)

    sid = client.post("/sets", json={
        "name": "Club nuit", "mode": "duration", "target": 1440,  # 6 x 240 s
        "curve_points": [[0.0, 2.0], [0.5, 9.0], [1.0, 4.0]], "n_slots": 6,
    }).json()["set_id"]

    client.put(f"/sets/{sid}/slots/0", json={"content_id": "anchor", "is_anchor": True})

    sugg = client.get(f"/sets/{sid}/slots/2/suggestions?limit=10").json()
    assert sugg, "suggestions non vides"
    assert all(0 <= s["score"] <= 100 for s in sugg)
    assert [s["score"] for s in sugg] == sorted([s["score"] for s in sugg], reverse=True)
    assert all("anchor" != s["content_id"] for s in sugg)
    for s in sugg:
        assert set(s["dimensions"]) == {"key", "bpm", "energy", "vibe", "ambiance"}
        assert all(lbl for lbl, _ in s["dimensions"].values())

    forced = client.post(f"/sets/{sid}/slots/3/force", json={"content_id": "clash"}).json()
    assert forced["impact"]["warnings"], "un morceau clashant doit lever des alertes"

    rec = client.get(f"/sets/{sid}").json()
    assert rec["slots"][0]["content_id"] == "anchor" and rec["slots"][0]["is_anchor"] is True
    assert rec["slots"][3]["content_id"] == "clash" and rec["slots"][3]["is_forced"] is True
    starts = [s["start_time_s"] for s in rec["slots"]]
    assert starts == sorted(starts), "temps de départ croissants"

    assert len(client.get("/galaxy").json()) == 6
