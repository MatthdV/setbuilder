"""Proximité de vibe entre deux morceaux via la similarité cosine de leurs
embeddings MuQ (continuité de son, le point fort de la Galaxy)."""

import numpy as np


def vibe_score(a: np.ndarray | None, b: np.ndarray | None) -> tuple[str, float]:
    """`(label, sous-score 0..1)`. Embedding absent / non fini / nul → ("vibe n/a", 0.5).

    cosine ∈ [-1, 1] mappé en [0, 1] par (cos + 1) / 2.
    """
    if a is None or b is None:
        return "vibe n/a", 0.5
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        return "vibe n/a", 0.5
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0.0 or nb == 0.0:
        return "vibe n/a", 0.5
    cos = float(np.dot(a, b) / (na * nb))
    score = max(0.0, min(1.0, (cos + 1.0) / 2.0))
    return f"vibe {round(score * 100)}%", score
