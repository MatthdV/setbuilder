"""Task 8 — smoke e2e : pending -> start -> status, via launcher fake écrivant `done`."""
import sqlite3

from fastapi.testclient import TestClient

from setbuilder.analyze_job import write_status
from setbuilder.api import create_app
from setbuilder.features_cache import open_features
from setbuilder.sets_repo import open_sets


def _client_with_fake_launcher(tmp_path):
    db = tmp_path / "setbuilder.db"
    c = sqlite3.connect(str(db))
    c.execute("""CREATE TABLE tracks (content_id TEXT PRIMARY KEY, file_path TEXT)""")
    open_features(c)
    open_sets(c)
    for i in range(3):
        c.execute("INSERT INTO tracks (content_id, file_path) VALUES (?, ?)",
                  (f"t{i}", f"/music/t{i}.wav"))
    c.commit()
    c.close()

    def launcher(cache_path, status_path):
        write_status(status_path, {"state": "done", "analyzed": 3, "total": 3, "failures": []})
        return 4242

    return TestClient(create_app(str(db), analyze_launcher=launcher, rekordbox_probe=lambda: False))


def test_analyze_flow_pending_start_status(tmp_path):
    client = _client_with_fake_launcher(tmp_path)
    assert client.get("/analyze/pending").json()["pending"] >= 1
    assert client.post("/analyze").status_code == 202
    assert client.get("/analyze/status").json()["state"] in ("running", "done")
