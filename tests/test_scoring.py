from setbuilder.scoring import (
    DEFAULT_WEIGHTS,
    SCORING_VERSION,
    Candidate,
    SlotContext,
    score_candidate,
)


def _cand(**kw):
    base = dict(
        content_id="c", title=None, artist=None, bpm=128.0, camelot="8A",
        energy=7, moment=None, ambiance=None, embedding=None,
    )
    base.update(kw)
    return Candidate(**base)


def test_perfect_match_scores_high():
    prev = _cand(content_id="p")
    ctx = SlotContext(prev=prev, target_energy=7.0)
    b = score_candidate(_cand(camelot="8A", bpm=128.0, energy=7), ctx)
    assert b.score >= 90
    assert "key" in b.dimensions and "bpm" in b.dimensions and "energy" in b.dimensions


def test_breakdown_is_explainable():
    ctx = SlotContext(prev=_cand(), target_energy=7.0)
    b = score_candidate(_cand(camelot="3B"), ctx)
    assert b.dimensions["key"][1] == 0.0


def test_first_slot_no_prev_neutralises_relative_dims():
    ctx = SlotContext(prev=None, target_energy=5.0)
    b = score_candidate(_cand(energy=5), ctx)
    assert b.dimensions["key"][1] == 0.5
    assert b.dimensions["bpm"][1] == 0.5


def test_missing_optional_dims_do_not_cap_score():
    # clé + bpm + énergie parfaits, vibe/ambiance absents -> ne doit pas plafonner à 85
    prev = _cand(content_id="p")
    ctx = SlotContext(prev=prev, target_energy=7.0)
    b = score_candidate(_cand(energy=7), ctx)
    assert b.score == 100


def test_weights_versioned_and_normalised():
    assert isinstance(SCORING_VERSION, str) and SCORING_VERSION
    total = (DEFAULT_WEIGHTS.key + DEFAULT_WEIGHTS.bpm + DEFAULT_WEIGHTS.energy
             + DEFAULT_WEIGHTS.vibe + DEFAULT_WEIGHTS.ambiance)
    assert abs(total - 1.0) < 1e-9
