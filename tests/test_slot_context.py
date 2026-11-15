from setbuilder.curve import EnergyCurve
from setbuilder.scoring import Candidate
from setbuilder.sets_repo import SetRecord, Slot
from setbuilder.slot_context import build_slot_context
from setbuilder.timeline import slot_position


def _cand(cid, e):
    return Candidate(cid, cid, "x", 128.0, "8A", e, None, None, None)


def _target(rec, idx, durations):
    curve = EnergyCurve.from_points(rec.curve_points)
    return curve.target_at(slot_position(idx, len(rec.slots), rec.mode, durations, rec.target))


def test_prev_is_last_filled_before_slot():
    rec = SetRecord("s", "n", "count", 3, [(0.0, 2.0), (1.0, 8.0)], "av1",
                    [Slot(0, "a", True, False), Slot(1, None, False, False), Slot(2, None, False, False)])
    by_id = {"a": _cand("a", 5)}
    ctx = build_slot_context(rec, 1, by_id, durations=[None, None, None])
    assert ctx.prev.content_id == "a"
    assert ctx.target_energy == _target(rec, 1, [None, None, None])


def test_prev_skips_empty_and_unknown():
    rec = SetRecord("s", "n", "count", 4, [(0.0, 5.0)], "av1",
                    [Slot(0, "a", False, False), Slot(1, "ghost", False, False),
                     Slot(2, None, False, False), Slot(3, None, False, False)])
    by_id = {"a": _cand("a", 5)}  # 'ghost' absent du cache
    ctx = build_slot_context(rec, 3, by_id, durations=[None] * 4)
    assert ctx.prev.content_id == "a"


def test_first_slot_has_no_prev():
    rec = SetRecord("s", "n", "count", 2, [(0.0, 5.0)], "av1",
                    [Slot(0, None, False, False), Slot(1, None, False, False)])
    ctx = build_slot_context(rec, 0, {}, durations=[None, None])
    assert ctx.prev is None
