import sqlite3

import pytest

from setbuilder.sets_repo import (
    clear_slot,
    create_set,
    delete_set,
    get_set,
    list_sets,
    open_sets,
    place_track,
)


def _c():
    c = sqlite3.connect(":memory:")
    open_sets(c)
    return c


def test_create_and_read_roundtrip():
    c = _c()
    sid = create_set(c, "Club 90", "count", 12, [(0.0, 2.0), (0.5, 9.0), (1.0, 4.0)], "av1", n_slots=12)
    rec = get_set(c, sid)
    assert rec.name == "Club 90" and rec.mode == "count" and len(rec.slots) == 12
    assert all(s.content_id is None for s in rec.slots)
    assert rec.curve_points[1] == (0.5, 9.0)
    assert [s.position for s in rec.slots] == list(range(12))


def test_place_and_clear():
    c = _c()
    sid = create_set(c, "x", "count", 3, [(0.0, 5.0)], "av1", n_slots=3)
    place_track(c, sid, 1, "trackA", is_anchor=True)
    assert get_set(c, sid).slots[1].content_id == "trackA"
    assert get_set(c, sid).slots[1].is_anchor is True
    clear_slot(c, sid, 1)
    assert get_set(c, sid).slots[1].content_id is None
    assert get_set(c, sid).slots[1].is_anchor is False


def test_invalid_mode_rejected():
    c = _c()
    with pytest.raises(ValueError):
        create_set(c, "x", "nope", 3, [(0.0, 5.0)], "av1", n_slots=3)


def test_delete_removes_set_and_slots():
    c = _c()
    sid = create_set(c, "x", "count", 2, [(0.0, 5.0)], "av1", n_slots=2)
    delete_set(c, sid)
    assert get_set(c, sid) is None and list_sets(c) == []


def test_get_unknown_set_is_none():
    assert get_set(_c(), "nope") is None
