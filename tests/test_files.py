import os
import unicodedata

from setbuilder.files import resolve_file


def test_resolve_ok_nfc_nfd(tmp_path):
    name_nfc = unicodedata.normalize("NFC", "Été.mp3")
    name_nfd = unicodedata.normalize("NFD", "Été.mp3")
    assert name_nfc != name_nfd

    (tmp_path / name_nfd).write_bytes(b"")
    requested = os.path.join(str(tmp_path), name_nfc)

    path, status = resolve_file(requested)

    assert status == "ok"
    assert path is not None
    assert os.path.exists(path)


def test_resolve_missing(tmp_path):
    requested = os.path.join(str(tmp_path), "absent.mp3")

    assert resolve_file(requested) == (None, "missing")


def _strict_exists(stored: str):
    """os.path.exists qui ne reconnaît qu'une seule forme Unicode exacte."""
    return lambda p: p == stored


def test_resolve_fallback_stored_nfc_queried_nfd(monkeypatch):
    stored = unicodedata.normalize("NFC", "/music/Été.mp3")
    queried = unicodedata.normalize("NFD", "/music/Été.mp3")
    monkeypatch.setattr("setbuilder.files.os.path.exists", _strict_exists(stored))

    assert resolve_file(queried) == (stored, "ok")


def test_resolve_fallback_stored_nfd_queried_nfc(monkeypatch):
    stored = unicodedata.normalize("NFD", "/music/Été.mp3")
    queried = unicodedata.normalize("NFC", "/music/Été.mp3")
    monkeypatch.setattr("setbuilder.files.os.path.exists", _strict_exists(stored))

    assert resolve_file(queried) == (stored, "ok")


def test_resolve_missing_when_no_form_exists(monkeypatch):
    monkeypatch.setattr("setbuilder.files.os.path.exists", lambda p: False)

    assert resolve_file("/music/Été.mp3") == (None, "missing")
