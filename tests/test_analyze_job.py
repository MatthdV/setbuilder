"""Task 3 — statut de job atomique, pid-aware.

read_status ne lève jamais : absent/corrompu -> idle ; running + pid non vivant
(mort, None, invalide) -> stale (dérivé à la lecture). write_status est atomique
et ne laisse pas de .tmp résiduel.
"""
import os

import pytest

from setbuilder import analyze_job as aj


def test_write_then_read_roundtrip(tmp_path):
    p = str(tmp_path / "s.json")
    aj.write_status(p, {"state": "done", "analyzed": 3})
    assert aj.read_status(p) == {"state": "done", "analyzed": 3}


def test_read_status_missing_returns_idle(tmp_path):
    assert aj.read_status(str(tmp_path / "nope.json")) == {"state": "idle"}


def test_read_status_corrupt_returns_idle(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{ not json")
    assert aj.read_status(str(p)) == {"state": "idle"}


def test_status_running_live_pid_stays_running(tmp_path):
    p = str(tmp_path / "s.json")
    aj.write_status(p, {"state": "running", "pid": os.getpid()})
    assert aj.read_status(p)["state"] == "running"


def test_status_running_dead_pid_is_stale(tmp_path):
    p = str(tmp_path / "s.json")
    aj.write_status(p, {"state": "running", "pid": 999999999})
    assert aj.read_status(p)["state"] == "stale"


def test_status_running_none_pid_is_stale(tmp_path):
    # claim orpheline : crash entre claim (pid:None) et ré-écriture du pid
    p = str(tmp_path / "s.json")
    aj.write_status(p, {"state": "running", "pid": None})
    assert aj.read_status(p)["state"] == "stale"


def test_pid_alive_none_is_false():
    assert aj.pid_alive(None) is False
    assert aj.pid_alive(0) is False
    assert aj.pid_alive(-5) is False
    assert aj.pid_alive("x") is False
    assert aj.pid_alive(os.getpid()) is True


def test_write_is_atomic_no_tmp_residue(tmp_path):
    p = str(tmp_path / "s.json")
    aj.write_status(p, {"state": "running", "pid": 1})
    leftovers = [f for f in os.listdir(tmp_path) if f != "s.json"]
    assert leftovers == []


def test_write_cleans_tmp_on_failure(tmp_path, monkeypatch):
    p = str(tmp_path / "s.json")

    def boom(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(aj.os, "replace", boom)
    with pytest.raises(OSError):
        aj.write_status(p, {"state": "running"})
    # aucun .tmp résiduel, et le fichier final n'a pas été créé
    assert os.listdir(tmp_path) == []
