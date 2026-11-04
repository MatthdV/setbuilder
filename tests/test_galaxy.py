import numpy as np

from setbuilder.galaxy import fit_umap


def _emb(n, seed=0):
    return np.random.default_rng(seed).normal(size=(n, 1024)).astype(np.float32)


def test_fit_umap_shape_and_determinism():
    x = _emb(50)
    a = fit_umap(x, seed=42)
    b = fit_umap(x, seed=42)
    assert a.shape == (50, 2)
    assert np.isfinite(a).all()
    assert np.allclose(a, b)


def test_fit_umap_few_points():
    for n in (0, 1, 2, 3, 5):
        out = fit_umap(_emb(n), seed=1)
        assert out.shape == (n, 2)
        assert np.isfinite(out).all()
