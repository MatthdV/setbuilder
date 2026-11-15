"""Smoke bout-en-bout : cache réaliste (embeddings MuQ) -> load -> rank."""
import sqlite3

import numpy as np

from setbuilder.candidates import load_candidates, rank
from setbuilder.curve import EnergyCurve
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.scoring import Candidate, SlotContext

_DIM = 1024


def _build_db():
    rng = np.random.default_rng(0)
    c = sqlite3.connect(":memory:")
    c.execute(
        """CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
           bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT)"""
    )
    open_features(c)
    anchor = rng.standard_normal(_DIM).astype(np.float32)
    # (id, bpm, camelot, energy, embedding) — 'ideal' colle à l'ancre et au contexte.
    specs = {
        "ideal":  (129.0, "8A", 6, anchor + 0.01 * rng.standard_normal(_DIM)),
        "clash":  (150.0, "3B", 2, rng.standard_normal(_DIM)),
        "okvibe": (124.0, "9A", 8, anchor + 0.5 * rng.standard_normal(_DIM)),
        "far":    (90.0, "6B", 9, rng.standard_normal(_DIM)),
        "mid":    (131.0, "8B", 5, rng.standard_normal(_DIM)),
    }
    for cid, (bpm, cam, en, emb) in specs.items():
        c.execute("INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?)",
                  (cid, cid, "x", bpm, cam, None, None, "techno"))
        upsert_features(c, cid, {
            "energy_score": en, "muq_embedding": emb.astype(np.float32),
            "analysis_version": "av1",
        })
    anchor_cand = Candidate(content_id="prev", title=None, artist=None, bpm=128.0,
                            camelot="8A", energy=6, moment=None, ambiance=None,
                            embedding=anchor)
    return c, anchor_cand


def test_end_to_end_ranking():
    cache, prev = _build_db()
    curve = EnergyCurve.from_points([(0.0, 2.0), (0.5, 9.0), (1.0, 4.0)])
    ctx = SlotContext(prev=prev, target_energy=curve.target_at(0.4))

    ranked = rank(load_candidates(cache, "av1"), ctx)

    assert ranked, "au moins un candidat classé"
    scores = [r.score for r in ranked]
    assert all(0 <= s <= 100 for s in scores)
    assert scores == sorted(scores, reverse=True)
    for r in ranked:
        assert set(r.dimensions) == {"key", "bpm", "energy", "vibe", "ambiance"}
        assert all(label for label, _ in r.dimensions.values())
    assert "ideal" in {r.content_id for r in ranked[:2]}
