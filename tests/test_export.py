import pytest

from setbuilder.export import backup_db, export_set


class _FakeDB:
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


def test_export_orders_tracks_and_commits():
    db = _FakeDB()
    out = export_set(db, "Club 90", ["a", "b", "c"])
    assert out == {"playlist": "Club 90", "n_tracks": 3}
    assert db.calls == [("create", "Club 90"), ("add", "a"), ("add", "b"), ("add", "c")]
    assert db.committed is True


def test_export_empty_rejected():
    with pytest.raises(ValueError):
        export_set(_FakeDB(), "x", [])


def test_backup_copies_master_db(tmp_path):
    src = tmp_path / "rb"
    src.mkdir()
    (src / "master.db").write_text("DBDATA")
    dest = backup_db(str(src), str(tmp_path / "backups"))
    import os

    assert os.path.isfile(os.path.join(dest, "master.db"))
    assert open(os.path.join(dest, "master.db")).read() == "DBDATA"


def test_backup_also_copies_playlists_xml(tmp_path):
    src = tmp_path / "rb"
    src.mkdir()
    (src / "master.db").write_text("DBDATA")
    (src / "masterPlaylists6.xml").write_text("XML")
    dest = backup_db(str(src), str(tmp_path / "backups"))
    import os

    assert os.path.isfile(os.path.join(dest, "masterPlaylists6.xml"))


def test_backup_missing_master_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_db(str(tmp_path / "nope"), str(tmp_path / "b"))
