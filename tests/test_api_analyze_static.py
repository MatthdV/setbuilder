"""Task 7 — assets du panneau d'analyse servis + référencés."""
import sqlite3

from fastapi.testclient import TestClient

from setbuilder.api import create_app
from setbuilder.features_cache import open_features
from setbuilder.sets_repo import open_sets


def _client(tmp_path):
    db = tmp_path / "setbuilder.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE tracks (content_id TEXT PRIMARY KEY, file_path TEXT)")
    open_features(c)
    open_sets(c)
    c.commit()
    c.close()
    return TestClient(create_app(str(db)))


def test_analyze_js_served(tmp_path):
    assert _client(tmp_path).get("/static/analyze.js").status_code == 200


def test_index_references_analyze_js(tmp_path):
    html = _client(tmp_path).get("/").text
    assert "/static/analyze.js" in html
