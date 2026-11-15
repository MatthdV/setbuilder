import numpy as np

from setbuilder.muq_analyze import mean_pool, split_segments


def test_mean_pool():
    rng = np.random.default_rng(0)
    hidden = rng.normal(size=(7, 1024)).astype(np.float32)
    out = mean_pool(hidden)
    assert out.shape == (1024,)
    assert np.allclose(out, hidden.mean(axis=0))


def test_mean_pool_empty_and_invalid():
    assert mean_pool(np.zeros((0, 1024), dtype=np.float32)) is None
    assert mean_pool(np.zeros(1024, dtype=np.float32)) is None  # 1D invalide
    assert mean_pool(np.zeros((3, 1024, 2), dtype=np.float32)) is None
    assert mean_pool(np.full((2, 4), np.nan, dtype=np.float32)) is None  # pas de NaN silencieux


def test_split_segments():
    audio = np.arange(25, dtype=np.float32)
    segs = split_segments(audio, 10, min_len=4)
    assert [len(s) for s in segs] == [10, 10, 5]
    # reste trop court : fusionné/ignoré, jamais de segment < min_len
    segs = split_segments(np.arange(22, dtype=np.float32), 10, min_len=4)
    assert all(len(s) >= 4 for s in segs) and sum(len(s) for s in segs) >= 20
    assert split_segments(np.zeros(0, dtype=np.float32), 10, min_len=4) == []
