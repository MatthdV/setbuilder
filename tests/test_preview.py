import shutil
import sqlite3

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from setbuilder.api import create_app
from tests.test_api_robustness import _db


def _client(tmp_path, files):
    path = _db(tmp_path)
    c = sqlite3.connect(path)
    c.execute("ALTER TABLE tracks ADD COLUMN file_path TEXT")
    for cid, fp in files.items():
        c.execute("UPDATE tracks SET file_path = ? WHERE content_id = ?", (fp, cid))
    c.commit()
    c.close()
    return TestClient(create_app(path, preview_cache_dir=str(tmp_path / 'pvcache')),
                      raise_server_exceptions=False)


def _tone(path, fmt, seconds=3, sr=22050):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    sf.write(str(path), 0.2 * np.sin(2 * np.pi * 440 * t), sr, format=fmt)


def test_native_wav_streams_with_range(tmp_path):
    wav = tmp_path / "a.wav"
    _tone(wav, "WAV")
    client = _client(tmp_path, {"a": str(wav)})
    info = client.get("/tracks/a/preview-info").json()
    assert info["native"] is True
    r = client.get("/tracks/a/preview")
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    r = client.get("/tracks/a/preview", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg absent")
def test_aiff_is_transcoded_to_mp3_excerpt(tmp_path):
    aiff = tmp_path / "b.aiff"
    _tone(aiff, "AIFF")
    client = _client(tmp_path, {"b": str(aiff)})
    assert client.get("/tracks/b/preview-info").json()["native"] is False
    r = client.get("/tracks/b/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg"
    assert len(r.content) > 1000
    # le mp3 complet est mis en cache et seekable (Range) : pas de limite de 2 minutes
    assert list((tmp_path / "pvcache").glob("b-*.mp3"))
    r2 = client.get("/tracks/b/preview", headers={"Range": "bytes=100-199"})
    assert r2.status_code == 206 and len(r2.content) == 100


def test_preview_errors(tmp_path):
    client = _client(tmp_path, {"a": str(tmp_path / "nope.wav")})
    assert client.get("/tracks/zzz/preview").status_code == 404           # id inconnu
    r = client.get("/tracks/a/preview")                                    # fichier absent
    assert r.status_code == 404 and r.json()["detail"] == "file_missing"
    assert client.get("/tracks/b/preview").status_code == 404              # pas de file_path


def test_cross_site_fetch_rejected(tmp_path):
    wav = tmp_path / "a.wav"
    _tone(wav, "WAV")
    client = _client(tmp_path, {"a": str(wav)})
    assert client.get("/tracks/a/preview", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get("/tracks/a/preview", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
