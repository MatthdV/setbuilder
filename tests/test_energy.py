from setbuilder.energy import energy_score


def test_energy_score_bounds():
    assert energy_score(0.0, 0.0) == 1
    assert energy_score(1.0, 1.0) == 10


def test_energy_score_monotonic():
    scores = [energy_score(a / 10, 0.5) for a in range(11)]
    assert scores == sorted(scores)
    scores = [energy_score(0.5, l / 10) for l in range(11)]
    assert scores == sorted(scores)


def test_energy_score_clamps_out_of_range():
    assert energy_score(-5, -5) == 1
    assert energy_score(7, 7) == 10
    assert 1 <= energy_score(0.4, 2.0) <= 10
