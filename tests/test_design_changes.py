"""Décisions de design : presets de courbe par type de set, doublons, slots
protégés, échecs d'analyse hors compteur, export sans doublon de nom."""
import sqlite3

import numpy as np
import pytest
from fastapi.testclient import TestClient

from setbuilder.analyze import Analyzers, count_pending, run_analyze
from setbuilder.api import create_app
from setbuilder.cache import open_cache
from setbuilder.curve import PRESETS
from setbuilder.essentia_analyze import build_features
from setbuilder.export import export_set
from setbuilder.features_cache import open_features
from setbuilder.sets_repo import open_sets
from tests.test_api_robustness import _client, _db


def _mk(client, **body):
    base = {"name": "x", "mode": "count", "target": 4, "n_slots": 4}
    return client.post("/sets", json={**base, **body})


# --- presets -------------------------------------------------------------------

def test_presets_are_distinct_and_valid():
    assert set(PRESETS) == {"warmup", "main", "closing", "after"}
    assert len({tuple(map(tuple, v)) for v in PRESETS.values()}) == 4
    for pts in PRESETS.values():
        assert all(0 <= x <= 1 and 0 <= e <= 10 for x, e in pts)


@pytest.mark.parametrize("kind", ["warmup", "main", "closing", "after"])
def test_create_set_from_preset(tmp_path, kind):
    client = _client(tmp_path)
    sid = _mk(client, set_type=kind).json()["set_id"]
    rec = client.get(f"/sets/{sid}").json()
    assert rec["set_type"] == kind
    assert [list(p) for p in rec["curve_points"]] == [list(map(float, p)) for p in PRESETS[kind]]


def test_set_requires_type_or_curve(tmp_path):
    client = _client(tmp_path)
    assert _mk(client).status_code == 422
    assert _mk(client, set_type="bogus").status_code == 422
    r = _mk(client, curve_points=[[0, 3], [1, 6]])  # courbe perso, sans type
    assert r.status_code == 200
    assert client.get(f"/sets/{r.json()['set_id']}").json()["set_type"] == "custom"


def test_old_sets_table_gets_set_type_column(tmp_path):
    c = sqlite3.connect(str(tmp_path / "old.db"))
    c.execute("CREATE TABLE sets (set_id TEXT PRIMARY KEY, name TEXT, mode TEXT, target REAL, "
              "curve_json TEXT, analysis_version TEXT, created_at TEXT)")
    c.execute("CREATE TABLE set_slots (set_id TEXT, position INTEGER, content_id TEXT, "
              "is_anchor INTEGER DEFAULT 0, is_forced INTEGER DEFAULT 0, PRIMARY KEY (set_id, position))")
    c.execute("INSERT INTO sets VALUES ('s','n','count',3,'[[0,5]]','av1','2026-01-01')")
    open_sets(c)
    assert c.execute("SELECT set_type FROM sets").fetchone()[0] is None


# --- doublons + slots protégés ---------------------------------------------------

def _set(client):
    return _mk(client, set_type="main").json()["set_id"]


def test_duplicate_track_rejected_409(tmp_path):
    client = _client(tmp_path)
    sid = _set(client)
    assert client.put(f"/sets/{sid}/slots/0", json={"content_id": "a"}).status_code == 200
    assert client.put(f"/sets/{sid}/slots/0", json={"content_id": "a"}).status_code == 200  # même slot
    r = client.put(f"/sets/{sid}/slots/1", json={"content_id": "a"})
    assert r.status_code == 409 and r.json()["detail"] == "duplicate_track"
    r = client.post(f"/sets/{sid}/slots/1/force", json={"content_id": "a"})
    assert r.status_code == 409 and r.json()["detail"] == "duplicate_track"


def test_protected_slot_needs_overwrite(tmp_path):
    client = _client(tmp_path)
    sid = _set(client)
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a", "is_anchor": True})
    r = client.put(f"/sets/{sid}/slots/0", json={"content_id": "b"})
    assert r.status_code == 409 and r.json()["detail"] == "slot_protected"
    assert client.put(f"/sets/{sid}/slots/0", json={"content_id": "b", "overwrite": True}).status_code == 200
    client.post(f"/sets/{sid}/slots/1/force", json={"content_id": "c"})
    r = client.post(f"/sets/{sid}/slots/1/force", json={"content_id": "a"})
    assert r.status_code == 409 and r.json()["detail"] == "slot_protected"
    r = client.post(f"/sets/{sid}/slots/1/force", json={"content_id": "a", "overwrite": True})
    assert r.status_code == 200
    # slot non protégé : écrasement libre
    client.put(f"/sets/{sid}/slots/2", json={"content_id": "c"})
    assert client.put(f"/sets/{sid}/slots/2", json={"content_id": "b"}).status_code in (200, 409)


# --- échecs d'analyse hors du compteur ---------------------------------------------

class _Fakes:
    def load_audio(self, path):
        return np.full(16000, float(len(path)), np.float32)

    def essentia(self, audio):
        if len(audio) and audio[0] == 6.0:  # "bd.mp3" -> échec
            raise ValueError("boom")
        return build_features({"genre_probs": {"House": 0.9}, "arousal": 0.5, "loudness_norm": 0.5})

    def muq(self, audio):
        return np.ones(16, np.float32)


def test_failed_tracks_leave_pending(tmp_path):
    conn = open_cache(str(tmp_path / "s.db"))
    open_features(conn)
    for cid, p in [("1", "ok1.mp3"), ("2", "bd.mp3"), ("3", "ok333.mp3")]:
        conn.execute("INSERT INTO tracks (content_id, file_path) VALUES (?, ?)", (cid, p))
    conn.commit()
    assert count_pending(conn)[0] == 3
    stats = run_analyze(conn, analyzers=_Fakes())
    assert stats.failed == 1
    pending, total = count_pending(conn)
    assert (pending, total) == (0, 3)
    again = run_analyze(conn, analyzers=_Fakes())  # pas de nouvel essai du morceau KO
    assert again.failed == 0


def test_pending_endpoint_reports_failed(tmp_path):
    client = TestClient(create_app(str(tmp_path / "new.db")))
    assert client.get("/analyze/pending").json()["failed"] == 0


# --- export : pas de playlist en double ----------------------------------------------

class _RB:
    def __init__(self, existing):
        self.existing, self.created = existing, None

    def get_playlist(self):
        return [type("P", (), {"Name": n})() for n in self.existing]

    def create_playlist(self, name, **kw):
        self.created = name
        return {"name": name}

    def add_to_playlist(self, pl, cid):
        pass

    def commit(self):
        pass


def test_export_suffixes_existing_name():
    rb = _RB(["Club", "Club (2)"])
    assert export_set(rb, "Club", ["a"])["playlist"] == "Club (3)"
    assert rb.created == "Club (3)"
    assert export_set(_RB([]), "Club", ["a"])["playlist"] == "Club"
