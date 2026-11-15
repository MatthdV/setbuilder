import numpy as np

from setbuilder.cache import open_cache
from setbuilder.features_cache import has_features, open_features, upsert_features

FEATURE_COLS = [
    "content_id", "top_genre", "genres_json", "mood_happy", "mood_sad", "mood_party",
    "mood_relaxed", "mood_aggressive", "valence", "arousal", "energy_score",
    "muq_embedding", "muq_dim", "analysis_version", "analyzed_at",
]
GALAXY_COLS = ["content_id", "umap_x", "umap_y", "umap_version"]


def test_open_features_creates_schema(tmp_path):
    conn = open_cache(str(tmp_path / "s.db"))
    open_features(conn)
    open_features(conn)  # idempotent
    f = conn.execute("PRAGMA table_info(features)").fetchall()
    g = conn.execute("PRAGMA table_info(galaxy)").fetchall()
    assert [r[1] for r in f] == FEATURE_COLS
    assert [r[1] for r in g] == GALAXY_COLS
    assert [r[1] for r in f if r[5]] == ["content_id"]
    assert [r[1] for r in g if r[5]] == ["content_id"]


def test_upsert_and_has_features(tmp_path):
    conn = open_cache(str(tmp_path / "s.db"))
    open_features(conn)
    emb = np.arange(4, dtype=np.float32)
    upsert_features(conn, "1", {"top_genre": "House", "energy_score": 7,
                                "muq_embedding": emb, "analysis_version": "v1"})
    assert has_features(conn, "1", "v1")
    assert not has_features(conn, "1", "v2")
    assert not has_features(conn, "2", "v1")

    upsert_features(conn, "1", {"top_genre": "Techno", "analysis_version": "v1"})
    rows = conn.execute("SELECT top_genre, muq_dim FROM features").fetchall()
    assert len(rows) == 1 and rows[0][0] == "Techno"

    upsert_features(conn, "1", {"muq_embedding": emb, "analysis_version": "v1"})
    blob, dim = conn.execute("SELECT muq_embedding, muq_dim FROM features").fetchone()
    assert dim == 4
    assert np.array_equal(np.frombuffer(blob, dtype=np.float32), emb)
