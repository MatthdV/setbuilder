import pytest

from setbuilder.curve import EnergyCurve


def test_linear_interpolation():
    c = EnergyCurve.from_points([(0.0, 2.0), (0.5, 8.0), (1.0, 4.0)])
    assert c.target_at(0.0) == 2.0
    assert c.target_at(0.5) == 8.0
    assert c.target_at(0.25) == 5.0


def test_position_clamped_not_extrapolated():
    c = EnergyCurve.from_points([(0.0, 2.0), (1.0, 9.0)])
    assert c.target_at(-0.5) == 2.0
    assert c.target_at(1.5) == 9.0


def test_single_point_is_flat():
    c = EnergyCurve.from_points([(0.0, 6.0)])
    assert c.target_at(0.3) == 6.0


def test_points_sorted_regardless_of_input_order():
    c = EnergyCurve.from_points([(1.0, 4.0), (0.0, 2.0)])
    assert c.target_at(0.0) == 2.0


def test_empty_rejected():
    with pytest.raises(ValueError):
        EnergyCurve.from_points([])
