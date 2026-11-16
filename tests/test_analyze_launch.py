"""Task 5 — launcher sous-process détaché pour l'analyse."""
import sys

from setbuilder.analyze_launch import spawn_analyze


def test_spawn_analyze_builds_detached_command(monkeypatch):
    seen = {}

    class _FakePopen:
        def __init__(self, cmd, **kw):
            seen.update(cmd=cmd, kw=kw)
            self.pid = 4242

    monkeypatch.setattr("setbuilder.analyze_launch.subprocess.Popen", _FakePopen)
    assert spawn_analyze("/db", "/s.json") == 4242
    assert seen["cmd"][:4] == [sys.executable, "-m", "setbuilder", "analyze"]
    assert "--cache" in seen["cmd"] and "/db" in seen["cmd"]
    assert "--status-file" in seen["cmd"] and "/s.json" in seen["cmd"]
    assert seen["kw"]["start_new_session"] is True
