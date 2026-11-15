from setbuilder.timeline import slot_position, slot_start_times


def test_count_mode_even_spacing():
    assert slot_position(0, 4, "count", [None] * 4, 4) == 0.0
    assert slot_position(3, 4, "count", [None] * 4, 4) == 1.0
    assert slot_position(1, 4, "count", [None] * 4, 4) == 1 / 3


def test_count_single_slot_no_div_zero():
    assert slot_position(0, 1, "count", [None], 1) == 0.0


def test_duration_mode_by_cumulative_time():
    durs = [120.0, 180.0, 300.0]
    assert slot_position(2, 3, "duration", durs, 600.0) == 0.5


def test_duration_empty_slot_counts_zero():
    durs = [120.0, None, 300.0]
    assert slot_position(2, 3, "duration", durs, 600.0) == 120.0 / 600.0


def test_duration_clamped_to_one():
    assert slot_position(2, 3, "duration", [500.0, 500.0, 100.0], 600.0) == 1.0


def test_start_times_cumulative():
    assert slot_start_times([120.0, None, 300.0]) == [0.0, 120.0, 120.0]
