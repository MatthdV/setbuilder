import builtins

from setbuilder import __main__ as cli


def test_sync_refuses_when_rekordbox_running(monkeypatch, capsys):
    monkeypatch.setattr(cli, "rekordbox_running", lambda: True)
    real_import = builtins.__import__

    def guarded(name, *a, **k):
        if name.startswith("pyrekordbox"):
            raise AssertionError("pyrekordbox imported despite Rekordbox running")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", guarded)
    assert cli.main(["sync"]) == 1
    assert "Rekordbox" in capsys.readouterr().err


def test_analyze_refuses_when_rekordbox_running(monkeypatch, capsys):
    monkeypatch.setattr(cli, "rekordbox_running", lambda: True)
    monkeypatch.setattr(cli, "build_real_analyzers",
                        lambda: (_ for _ in ()).throw(AssertionError("models loaded")))
    assert cli.main(["analyze"]) == 1
    assert "Rekordbox" in capsys.readouterr().err


def test_analyze_runs_with_injected_analyzers(monkeypatch, tmp_path, capsys):
    import numpy as np

    from setbuilder.analyze import Analyzers
    from setbuilder.cache import open_cache
    from setbuilder.essentia_analyze import build_features

    db = tmp_path / "s.db"
    conn = open_cache(str(db))
    conn.execute("INSERT INTO tracks (content_id, file_path) VALUES ('1', '/x.wav')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(cli, "rekordbox_running", lambda: False)
    monkeypatch.setattr(cli, "build_real_analyzers", lambda: Analyzers(
        essentia=lambda a: build_features({"arousal": 0.5}),
        muq=lambda a: np.ones(8, dtype=np.float32),
        load_audio=lambda p: np.ones(100, dtype=np.float32)))
    assert cli.main(["analyze", "--cache", str(db)]) == 0
    assert "1 analysés" in capsys.readouterr().out


def test_analyze_clean_error_when_models_unavailable(monkeypatch, tmp_path, capsys):
    from setbuilder.errors import AnalysisUnavailableError

    monkeypatch.setattr(cli, "rekordbox_running", lambda: False)

    def boom():
        raise AnalysisUnavailableError("hors-ligne")

    monkeypatch.setattr(cli, "build_real_analyzers", boom)
    assert cli.main(["analyze", "--cache", str(tmp_path / "s.db")]) == 2
    assert "hors-ligne" in capsys.readouterr().err
