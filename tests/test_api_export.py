import sqlite3

from fastapi.testclient import TestClient

from setbuilder.api import create_app
from setbuilder.features_cache import open_features
from setbuilder.sets_repo import open_sets


class _FakeRB:
    def __init__(self):
        self.calls = []
        self.committed = False

    def create_playlist(self, name, **kw):
        self.calls.append(("create", name))
        return {"name": name}

    def add_to_playlist(self, pl, cid):
        self.calls.append(("add", cid))

    def commit(self):
        self.committed = True


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


def _client(tmp_path, rb_provider):
    db = tmp_path / "setbuilder.db"
    _make_db(str(db))
    return TestClient(create_app(str(db), rb_provider=rb_provider))


def _rb_dir_with_master(tmp_path):
    rbdir = tmp_path / "rb"
    rbdir.mkdir()
    (rbdir / "master.db").write_text("DBDATA")
    return rbdir


def test_export_endpoint_builds_playlist(tmp_path):
    fake = _FakeRB()
    rbdir = _rb_dir_with_master(tmp_path)
    client = _client(tmp_path, lambda: (str(rbdir), lambda: fake))

    sid = client.post("/sets", json={"name": "Club 90", "mode": "count", "target": 3,
                                     "curve_points": [[0, 2], [1, 8]], "n_slots": 3}).json()["set_id"]
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a", "is_anchor": True})
    client.put(f"/sets/{sid}/slots/2", json={"content_id": "c"})

    r = client.post(f"/sets/{sid}/export")
    assert r.status_code == 200
    body = r.json()
    assert body["n_tracks"] == 2
    assert body["playlist"] == "Club 90"
    assert "backup" in body
    # ordre respecte : slot 0 puis slot 2 (slot 1 vide saute)
    assert fake.calls == [("create", "Club 90"), ("add", "a"), ("add", "c")]
    assert fake.committed is True


def test_export_empty_set_400(tmp_path):
    fake = _FakeRB()
    rbdir = _rb_dir_with_master(tmp_path)
    client = _client(tmp_path, lambda: (str(rbdir), lambda: fake))
    sid = client.post("/sets", json={"name": "Vide", "mode": "count", "target": 2,
                                     "curve_points": [[0, 5]], "n_slots": 2}).json()["set_id"]
    assert client.post(f"/sets/{sid}/export").status_code == 400


def test_export_unknown_set_404(tmp_path):
    fake = _FakeRB()
    client = _client(tmp_path, lambda: (str(tmp_path), lambda: fake))
    assert client.post("/sets/nope/export").status_code == 404


def test_export_lock_error_409(tmp_path):
    rbdir = _rb_dir_with_master(tmp_path)
    client = _client(tmp_path, lambda: (str(rbdir), _LockedRB))
    sid = client.post("/sets", json={"name": "Lock", "mode": "count", "target": 2,
                                     "curve_points": [[0, 5]], "n_slots": 2}).json()["set_id"]
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a"})
    r = client.post(f"/sets/{sid}/export")
    assert r.status_code == 409
    assert "Rekordbox" in r.json()["detail"]


def test_export_other_error_500(tmp_path):
    # erreur non-verrou -> 500, pas un 409 trompeur
    rbdir = _rb_dir_with_master(tmp_path)
    client = _client(tmp_path, lambda: (str(rbdir), _BoomRB))
    sid = client.post("/sets", json={"name": "Boom", "mode": "count", "target": 2,
                                     "curve_points": [[0, 5]], "n_slots": 2}).json()["set_id"]
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a"})
    assert client.post(f"/sets/{sid}/export").status_code == 500


class _LockedRB:
    def create_playlist(self, name, **kw):
        raise RuntimeError("database is locked")

    def add_to_playlist(self, pl, cid):
        pass

    def commit(self):
        pass


class _BoomRB:
    def create_playlist(self, name, **kw):
        raise RuntimeError("disk full")

    def add_to_playlist(self, pl, cid):
        pass

    def commit(self):
        pass


def test_export_missing_extra_503(tmp_path):
    def provider():
        raise ImportError("pyrekordbox manquant")

    client = _client(tmp_path, provider)
    sid = client.post("/sets", json={"name": "NoExtra", "mode": "count", "target": 2,
                                     "curve_points": [[0, 5]], "n_slots": 2}).json()["set_id"]
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a"})
    assert client.post(f"/sets/{sid}/export").status_code == 503


class _ClosingRB:
    def __init__(self):
        self.closed = False

    def create_playlist(self, name, **kw):
        return {"name": name}

    def add_to_playlist(self, pl, cid):
        pass

    def commit(self):
        pass

    def close(self):
        self.closed = True


class _ClosingBoomRB(_ClosingRB):
    def create_playlist(self, name, **kw):
        raise RuntimeError("disk full")


def test_export_closes_db_on_success(tmp_path):
    fake = _ClosingRB()
    rbdir = _rb_dir_with_master(tmp_path)
    client = _client(tmp_path, lambda: (str(rbdir), lambda: fake))
    sid = client.post("/sets", json={"name": "Close", "mode": "count", "target": 2,
                                     "curve_points": [[0, 5]], "n_slots": 2}).json()["set_id"]
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a"})
    assert client.post(f"/sets/{sid}/export").status_code == 200
    assert fake.closed is True


def test_export_closes_db_on_failure(tmp_path):
    # meme sur echec, la base Rekordbox est fermee (pas de lock retenu)
    fake = _ClosingBoomRB()
    rbdir = _rb_dir_with_master(tmp_path)
    client = _client(tmp_path, lambda: (str(rbdir), lambda: fake))
    sid = client.post("/sets", json={"name": "CloseBoom", "mode": "count", "target": 2,
                                     "curve_points": [[0, 5]], "n_slots": 2}).json()["set_id"]
    client.put(f"/sets/{sid}/slots/0", json={"content_id": "a"})
    assert client.post(f"/sets/{sid}/export").status_code == 500
    assert fake.closed is True
