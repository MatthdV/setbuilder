import numpy as np
import pytest

from setbuilder.analyze import ANALYSIS_VERSION, Analyzers, run_analyze
from setbuilder.cache import open_cache
from setbuilder.errors import AnalysisUnavailableError
from setbuilder.essentia_analyze import build_features
from setbuilder.features_cache import has_features, open_features


def _cache(tmp_path, paths):
    conn = open_cache(str(tmp_path / "s.db"))
    open_features(conn)
    for i, p in enumerate(paths, 1):
        conn.execute("INSERT INTO tracks (content_id, file_path) VALUES (?, ?)", (str(i), p))
    conn.commit()
    return conn


def _val(path):
    return float(sum(map(ord, path)))


class Fakes:
    def __init__(self, missing=(), boom=()):
        self.missing, self.boom = set(missing), set(boom)
        self.calls = 0

    def load_audio(self, path):
        return None if path in self.missing else np.full(16000, _val(path), np.float32)

    def essentia(self, audio):
        self.calls += 1
        if audio[0] in {_val(b) for b in self.boom}:
            raise ValueError("boom")
        return build_features({"genre_probs": {"House": 0.9}, "arousal": 0.5, "loudness_norm": 0.5})

    def muq(self, audio):
        rng = np.random.default_rng(int(audio[0]))
        return rng.normal(size=16).astype(np.float32)

    def analyzers(self):
        return Analyzers(essentia=self.essentia, muq=self.muq, load_audio=self.load_audio)


def test_run_analyze_incremental(tmp_path):
    cache = _cache(tmp_path, ["/a/one.wav", "/a/gone.wav", "/a/three.wav"])
    fk = Fakes(missing={"/a/gone.wav"})

    s1 = run_analyze(cache, analyzers=fk.analyzers(), analysis_version=ANALYSIS_VERSION)
    assert (s1.analyzed, s1.skipped, s1.missing, s1.failed) == (2, 0, 1, 0)
    assert has_features(cache, "1", ANALYSIS_VERSION) and has_features(cache, "3", ANALYSIS_VERSION)
    assert not has_features(cache, "2", ANALYSIS_VERSION)
    galaxy_ids = {r[0] for r in cache.execute("SELECT content_id FROM galaxy")}
    assert galaxy_ids == {"1", "3"}

    calls_before = fk.calls
    s2 = run_analyze(cache, analyzers=fk.analyzers(), analysis_version=ANALYSIS_VERSION)
    assert (s2.analyzed, s2.skipped, s2.missing) == (0, 2, 1)
    assert fk.calls == calls_before  # zéro recalcul

    # nouvelle version d'analyse -> tout est recalculé
    s3 = run_analyze(cache, analyzers=fk.analyzers(), analysis_version="v-next")
    assert s3.analyzed == 2 and s3.skipped == 0


def test_run_analyze_continues_on_missing(tmp_path):
    cache = _cache(tmp_path, ["/a/gone.wav", "/a/ok.wav", None])
    fk = Fakes(missing={"/a/gone.wav"})
    s = run_analyze(cache, analyzers=fk.analyzers(), analysis_version="v1")
    assert (s.analyzed, s.missing) == (1, 2)  # fichier disparu + file_path NULL
    assert has_features(cache, "2", "v1")


def test_run_analyze_counts_failure(tmp_path):
    cache = _cache(tmp_path, ["/a/ok1.wav", "/a/bad.wav", "/a/ok2.wav"])
    fk = Fakes(boom={"/a/bad.wav"})
    s = run_analyze(cache, analyzers=fk.analyzers(), analysis_version="v1")
    assert (s.analyzed, s.failed) == (2, 1)
    assert not has_features(cache, "2", "v1")


def test_run_analyze_none_embedding_is_failure_not_nan(tmp_path):
    cache = _cache(tmp_path, ["/a/short.wav"])
    fk = Fakes()
    an = Analyzers(essentia=fk.essentia, muq=lambda a: None, load_audio=fk.load_audio)
    s = run_analyze(cache, analyzers=an, analysis_version="v1")
    assert (s.analyzed, s.failed) == (0, 1)
    assert not has_features(cache, "1", "v1")


def test_run_analyze_aborts_when_models_unavailable(tmp_path):
    cache = _cache(tmp_path, ["/a/one.wav", "/a/two.wav"])
    fk = Fakes()

    def offline(_audio):
        raise AnalysisUnavailableError("poids introuvables")

    an = Analyzers(essentia=offline, muq=fk.muq, load_audio=fk.load_audio)
    with pytest.raises(AnalysisUnavailableError, match="poids"):
        run_analyze(cache, analyzers=an, analysis_version="v1")
