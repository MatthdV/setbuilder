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
