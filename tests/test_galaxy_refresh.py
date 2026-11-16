"""Fix galaxy-stale : _refresh_galaxy purge les coords sans embedding courant.

Bug : après un changement d'ANALYSIS_VERSION (ou perte d'embedding), les lignes
`galaxy` des tracks qui n'ont plus d'embedding à la version courante restaient,
et /galaxy servait des coords périmées.
"""
import numpy as np
import pytest

from setbuilder import analyze as analyze_mod
from setbuilder.analyze import _refresh_galaxy
from setbuilder.cache import open_cache
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.galaxy import UMAP_VERSION


def _seed_feature(cache, cid, version):
    upsert_features(cache, cid, {
        "muq_embedding": np.random.default_rng(int(cid[-1])).normal(size=8).astype("float32"),
        "analysis_version": version,
    })


def _galaxy_ids(cache):
    return {r[0] for r in cache.execute("SELECT content_id FROM galaxy")}


def test_refresh_purges_orphan_galaxy_rows(tmp_path):
    cache = open_cache(str(tmp_path / "c.db"))
    open_features(cache)
    for cid in ("t0", "t1", "t2"):
        _seed_feature(cache, cid, "v1")
    # ligne galaxy orpheline : pas d'embedding à la version courante
    cache.execute("INSERT INTO galaxy VALUES ('zz', 9.0, 9.0, ?)", (UMAP_VERSION,))
    cache.commit()

    _refresh_galaxy(cache, "v1", force=True)
    assert _galaxy_ids(cache) == {"t0", "t1", "t2"}  # orpheline 'zz' purgée


def test_refresh_empties_galaxy_on_version_bump(tmp_path):
    cache = open_cache(str(tmp_path / "c.db"))
    open_features(cache)
    for cid in ("t0", "t1", "t2"):
        _seed_feature(cache, cid, "v1")
    _refresh_galaxy(cache, "v1", force=True)
    assert _galaxy_ids(cache) == {"t0", "t1", "t2"}

    # version bumpée, aucun embedding à v2 -> galaxy vidée (plus de coords périmées)
    _refresh_galaxy(cache, "v2", force=False)
    assert _galaxy_ids(cache) == set()


def test_refresh_recomputes_when_set_changed_despite_equal_count(tmp_path):
    # coïncidence de compte : 2 anciennes lignes, 2 nouveaux ids différents -> doit resync
    cache = open_cache(str(tmp_path / "c.db"))
    open_features(cache)
    cache.execute("INSERT INTO galaxy VALUES ('old0', 1.0, 1.0, ?)", (UMAP_VERSION,))
    cache.execute("INSERT INTO galaxy VALUES ('old1', 2.0, 2.0, ?)", (UMAP_VERSION,))
    for cid in ("t0", "t1"):
        _seed_feature(cache, cid, "v1")
    cache.commit()

    _refresh_galaxy(cache, "v1", force=False)  # force False, mais le set a changé
    assert _galaxy_ids(cache) == {"t0", "t1"}  # old0/old1 purgés, t0/t1 placés


def test_refresh_rolls_back_purge_if_fit_fails(tmp_path, monkeypatch):
    # purge + recompute = une transaction : si fit_umap échoue, la purge est annulée
    cache = open_cache(str(tmp_path / "c.db"))
    open_features(cache)
    for cid in ("t0", "t1"):
        _seed_feature(cache, cid, "v1")
    _refresh_galaxy(cache, "v1", force=True)
    cache.execute("INSERT INTO galaxy VALUES ('zz', 9.0, 9.0, ?)", (UMAP_VERSION,))  # orphelin
    cache.commit()

    def boom(_embs):
        raise RuntimeError("umap down")

    monkeypatch.setattr(analyze_mod, "fit_umap", boom)
    with pytest.raises(RuntimeError, match="umap down"):
        _refresh_galaxy(cache, "v1", force=True)
    # la purge de 'zz' a été rollback : pas d'état partiel visible
    assert "zz" in _galaxy_ids(cache)
