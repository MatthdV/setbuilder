"""Task 4 — CLI `analyze --status-file` : statut live + terminal sur sorties gérées.

Factory d'analyzers injectée via monkeypatch de build_real_analyzers (pas de torch).
Sans --status-file, aucun fichier n'est écrit (comportement historique).
"""
import numpy as np

from setbuilder import __main__ as cli
from setbuilder.analyze import Analyzers
from setbuilder.analyze_job import read_status
from setbuilder.cache import open_cache
from setbuilder.errors import AnalysisUnavailableError
from setbuilder.essentia_analyze import build_features


def _seed(tmp_path, paths):
    db = str(tmp_path / "s.db")
    conn = open_cache(db)
    for i, p in enumerate(paths, 1):
        conn.execute("INSERT INTO tracks (content_id, file_path) VALUES (?, ?)", (str(i), p))
    conn.commit()
    conn.close()
    return db


def _ok_analyzers():
    def load_audio(path):
        return np.full(16000, float(sum(map(ord, path or ""))), np.float32)

    def essentia(audio):
        return build_features({"genre_probs": {"House": 0.9}, "arousal": 0.5, "loudness_norm": 0.5})

    def muq(audio):
        return np.random.default_rng(1).normal(size=16).astype(np.float32)

    return Analyzers(essentia=essentia, muq=muq, load_audio=load_audio)


def _boom_analyzers(cid_boom_path):
    an = _ok_analyzers()
    base = an.essentia

    def essentia(audio):
        if audio[0] == float(sum(map(ord, cid_boom_path))):
            raise ValueError("boom")
        return base(audio)

    return Analyzers(essentia=essentia, muq=an.muq, load_audio=an.load_audio)


def _unavailable_analyzers():
    an = _ok_analyzers()

    def essentia(audio):
        raise AnalysisUnavailableError("poids introuvables")

    return Analyzers(essentia=essentia, muq=an.muq, load_audio=an.load_audio)


def test_cli_status_file_written_on_success(tmp_path, monkeypatch):
    db = _seed(tmp_path, ["/a/one.wav", "/a/two.wav"])
    sf = str(tmp_path / "status.json")
    monkeypatch.setattr(cli, "rekordbox_running", lambda: False)
    monkeypatch.setattr(cli, "build_real_analyzers", _ok_analyzers)
    rc = cli.main(["analyze", "--cache", db, "--status-file", sf])
    assert rc == 0
    st = read_status(sf)
    assert st["state"] == "done" and st["analyzed"] == 2


def test_cli_status_file_records_failures(tmp_path, monkeypatch):
    db = _seed(tmp_path, ["/a/ok.wav", "/a/bad.wav"])
    sf = str(tmp_path / "status.json")
    monkeypatch.setattr(cli, "rekordbox_running", lambda: False)
    monkeypatch.setattr(cli, "build_real_analyzers", lambda: _boom_analyzers("/a/bad.wav"))
    rc = cli.main(["analyze", "--cache", db, "--status-file", sf])
    assert rc == 0
    st = read_status(sf)
    assert st["state"] == "done" and st["failed"] == 1 and st["failures"]


def test_cli_status_file_records_unavailable(tmp_path, monkeypatch):
    db = _seed(tmp_path, ["/a/one.wav"])
    sf = str(tmp_path / "status.json")
    monkeypatch.setattr(cli, "rekordbox_running", lambda: False)
    monkeypatch.setattr(cli, "build_real_analyzers", _unavailable_analyzers)
    rc = cli.main(["analyze", "--cache", db, "--status-file", sf])
    assert rc == 2
    st = read_status(sf)
    assert st["state"] == "error" and "analysis" in st["message"].lower()


def test_cli_rekordbox_open_writes_error_status(tmp_path, monkeypatch):
    db = _seed(tmp_path, ["/a/one.wav"])
    sf = str(tmp_path / "status.json")
    monkeypatch.setattr(cli, "rekordbox_running", lambda: True)
    rc = cli.main(["analyze", "--cache", db, "--status-file", sf])
    assert rc == 1
    st = read_status(sf)
    assert st["state"] == "error" and "Rekordbox" in st["message"]


def test_cli_without_status_file_writes_nothing(tmp_path, monkeypatch):
    db = _seed(tmp_path, ["/a/one.wav"])
    monkeypatch.setattr(cli, "rekordbox_running", lambda: False)
    monkeypatch.setattr(cli, "build_real_analyzers", _ok_analyzers)
    rc = cli.main(["analyze", "--cache", db])
    assert rc == 0
    assert [f for f in __import__("os").listdir(tmp_path) if f.endswith(".json")] == []
