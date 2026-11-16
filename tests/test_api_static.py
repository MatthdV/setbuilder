import sqlite3

from fastapi.testclient import TestClient

from setbuilder.api import create_app
from setbuilder.features_cache import open_features
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
    c.commit()
    c.close()
    return TestClient(create_app(str(db)))


def test_root_serves_html(tmp_path):
    client = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "setbuilder" in r.text.lower()


def test_static_assets_served(tmp_path):
    client = _client(tmp_path)
    for asset in ("tokens.css", "app.css", "app.js", "curve.js", "timeline.js",
                  "suggestions.js", "galaxy.js"):
        r = client.get("/static/" + asset)
        assert r.status_code == 200, asset


def test_index_references_core_assets(tmp_path):
    client = _client(tmp_path)
    html = client.get("/").text
    assert "/static/app.js" in html
    assert "/static/tokens.css" in html
