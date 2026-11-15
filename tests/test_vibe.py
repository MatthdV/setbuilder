import numpy as np

from setbuilder.vibe import vibe_score


def test_same_vector_max():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    _, s = vibe_score(v, v)
    assert s == 1.0


def test_orthogonal_is_mid():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert vibe_score(a, b)[1] == 0.5


def test_opposite_is_zero():
    a = np.array([1.0, 0.0], dtype=np.float32)
    assert vibe_score(a, -a)[1] == 0.0


def test_missing_or_nonfinite_neutral():
    v = np.array([1.0, 0.0], dtype=np.float32)
    assert vibe_score(None, v) == ("vibe n/a", 0.5)
    assert vibe_score(np.array([np.nan, 0.0], dtype=np.float32), v) == ("vibe n/a", 0.5)
    assert vibe_score(np.array([0.0, 0.0], dtype=np.float32), v) == ("vibe n/a", 0.5)
