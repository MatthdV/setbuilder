import json

import numpy as np
import pytest

from setbuilder.energy import energy_score
from setbuilder.essentia_analyze import (
    MAX_GENRES,
    ModelUnavailableError,
    build_features,
    loudness_norm,
    to_cache_dict,
)

RAW = {
    "genre_probs": {"Electronic---House": 0.5, "Electronic---Techno": 0.3, "Rock---Punk": 0.01,
                    "Electronic---Deep House": 0.4, "Pop---Synth-pop": 0.05, "Jazz---Bop": 0.02,
                    "Hip Hop---Trap": 0.03},
    "mood_happy": 0.7, "mood_sad": 0.1, "mood_party": 0.9, "mood_relaxed": 0.2,
    "mood_aggressive": 0.3, "valence": 0.6, "arousal": 0.8, "loudness_norm": 0.9,
}


def test_build_features():
    f = build_features(RAW)
    assert f.top_genre == "Electronic---House"
    assert [g for g, _ in f.genres] == ["Electronic---House", "Electronic---Deep House",
                                        "Electronic---Techno", "Pop---Synth-pop",
                                        "Hip Hop---Trap"]
    assert len(f.genres) == MAX_GENRES
    assert all(f.genres[i][1] >= f.genres[i + 1][1] for i in range(len(f.genres) - 1))
    assert (f.mood_happy, f.mood_sad, f.mood_party) == (0.7, 0.1, 0.9)
    assert (f.mood_relaxed, f.mood_aggressive) == (0.2, 0.3)
    assert (f.valence, f.arousal) == (0.6, 0.8)
    assert f.energy_score == energy_score(0.8, 0.9)


def test_build_features_tolerates_missing():
    f = build_features({})
    assert f.top_genre is None and f.genres == []
    assert f.mood_happy is None and f.arousal is None and f.energy_score is None
    g = build_features({"arousal": 0.9})  # loudness manquant -> neutre
    assert g.energy_score == energy_score(0.9, 0.5)


def test_to_cache_dict_roundtrip():
    d = to_cache_dict(build_features(RAW))
    assert d["top_genre"] == "Electronic---House"
    assert json.loads(d["genres_json"])[0][0] == "Electronic---House"
    assert d["energy_score"] == energy_score(0.8, 0.9)


def test_loudness_norm_range():
    quiet = np.full(16000, 0.001, dtype=np.float32)
    loud = np.full(16000, 0.5, dtype=np.float32)
    assert 0.0 <= loudness_norm(quiet) < loudness_norm(loud) <= 1.0
    assert loudness_norm(np.zeros(100, dtype=np.float32)) == 0.0


def test_model_unavailable_message(monkeypatch, tmp_path):
    from setbuilder import essentia_analyze as ea

    monkeypatch.setenv("SETBUILDER_MODELS", str(tmp_path))
    monkeypatch.setattr(ea, "_download", lambda url, dest: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(ModelUnavailableError, match="hors-ligne|SETBUILDER_MODELS"):
        ea.ensure_model("discogs-effnet-bs64-1.pb")
