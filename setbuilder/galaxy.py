"""Projection UMAP 2D des embeddings MuQ (carte Galaxy)."""

import numpy as np

UMAP_VERSION = "umap-v1"


def fit_umap(embeddings: np.ndarray, seed: int = 42) -> np.ndarray:
    """(N, D) -> (N, 2). n_neighbors clampé à min(15, N-1) ; N < 4 renvoie des coords triviales."""
    n = len(embeddings)
    if n < 4:  # UMAP (spectral init) est instable en dessous : placement trivial sur une ligne
        out = np.zeros((n, 2), dtype=np.float32)
        out[:, 0] = np.arange(n, dtype=np.float32)
        return out

    import umap  # import paresseux

    reducer = umap.UMAP(
        n_components=2,
        n_neighbors=max(2, min(15, n - 1)),
        random_state=seed,
        init="random" if n < 10 else "spectral",
    )
    return np.asarray(reducer.fit_transform(embeddings), dtype=np.float32)
