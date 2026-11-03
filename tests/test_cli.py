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
