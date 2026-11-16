"""Task 6 — endpoints /analyze, /analyze/status, /analyze/pending (single-run).

Launcher et probe Rekordbox injectés. Le lock sérialise claim->spawn->CAS ;
un 2e POST concurrent reçoit 409. pid mort ou claim orpheline -> relançable.
"""
import os
import threading

from fastapi.testclient import TestClient

from setbuilder.analyze_job import status_path_for, write_status
from setbuilder.api import create_app
from setbuilder.cache import open_cache


def _seed(tmp_path, paths):
    db = str(tmp_path / "setbuilder.db")
    conn = open_cache(db)
    for i, p in enumerate(paths, 1):
        conn.execute("INSERT INTO tracks (content_id, file_path) VALUES (?, ?)", (str(i), p))
    conn.commit()
    conn.close()
    return db


def _client(tmp_path, *, launcher=None, probe=None, paths=("/a/one.wav", "/a/two.wav")):
    db = _seed(tmp_path, list(paths))
    app = create_app(db, analyze_launcher=launcher, rekordbox_probe=probe or (lambda: False))
    return TestClient(app), db


def _live_launcher(calls):
    def launch(cache_path, status_path):
        calls.append(1)
        return os.getpid()  # pid vivant -> 2e POST voit "running" et 409
    return launch


def test_pending_counts_analyzable_tracks_only(tmp_path):
    client, _ = _client(tmp_path, paths=["/a/one.wav", None, ""])
    body = client.get("/analyze/pending").json()
    assert body == {"pending": 1, "total": 1}


def test_status_endpoint_returns_idle_when_no_file(tmp_path):
    client, _ = _client(tmp_path)
    assert client.get("/analyze/status").json()["state"] == "idle"


def test_analyze_starts_and_returns_202(tmp_path):
    calls = []
    client, db = _client(tmp_path, launcher=_live_launcher(calls))
    r = client.post("/analyze")
    assert r.status_code == 202 and r.json()["pid"] == os.getpid()
    assert calls == [1]
    st = client.get("/analyze/status").json()
    assert st["state"] == "running" and st["pid"] == os.getpid()


def test_analyze_rejects_double_run(tmp_path):
    calls = []
    client, _ = _client(tmp_path, launcher=_live_launcher(calls))
    assert client.post("/analyze").status_code == 202
    r2 = client.post("/analyze")
    assert r2.status_code == 409
    assert calls == [1]  # launcher appelé une seule fois


def test_concurrent_posts_spawn_once(tmp_path):
    calls = []
    client, _ = _client(tmp_path, launcher=_live_launcher(calls))
    codes = []

    def hit():
        codes.append(client.post("/analyze").status_code)

    ts = [threading.Thread(target=hit) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sorted(codes) == [202, 409]
    assert calls == [1]


def test_analyze_allows_restart_after_crash(tmp_path):
    calls = []
    client, db = _client(tmp_path, launcher=_live_launcher(calls))
    write_status(status_path_for(db), {"state": "running", "pid": 999999999})  # pid mort
    assert client.get("/analyze/status").json()["state"] == "stale"
    assert client.post("/analyze").status_code == 202
    assert calls == [1]


def test_analyze_allows_restart_after_orphan_claim(tmp_path):
    calls = []
    client, db = _client(tmp_path, launcher=_live_launcher(calls))
    write_status(status_path_for(db), {"state": "running", "pid": None})  # claim orpheline
    assert client.get("/analyze/status").json()["state"] == "stale"
    assert client.post("/analyze").status_code == 202


def test_post_spawn_pid_write_preserves_terminal_status(tmp_path):
    # launcher "rapide" : écrit done AVANT de renvoyer -> le CAS ne doit pas clobber
    def fast_launcher(cache_path, status_path):
        write_status(status_path, {"state": "done", "analyzed": 3, "total": 3, "failures": []})
        return os.getpid()

    client, db = _client(tmp_path, launcher=fast_launcher)
    assert client.post("/analyze").status_code == 202
    st = client.get("/analyze/status").json()
    assert st["state"] == "done" and st["analyzed"] == 3


def test_analyze_refuses_when_rekordbox_open(tmp_path):
    calls = []
    client, _ = _client(tmp_path, launcher=_live_launcher(calls), probe=lambda: True)
    r = client.post("/analyze")
    assert r.status_code == 409 and "Rekordbox" in r.json()["detail"]
    assert calls == []  # launcher jamais appelé
