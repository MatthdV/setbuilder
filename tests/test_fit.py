from setbuilder.fit import energy_fit, tag_bonus


def test_energy_on_target_perfect():
    assert energy_fit(8, 8.0)[1] == 1.0


def test_energy_gap_direction_labelled():
    assert "↗" in energy_fit(5, 8.0)[0]
    assert "↘" in energy_fit(9, 6.0)[0]


def test_energy_far_low_score():
    assert energy_fit(1, 10.0)[1] == 0.0


def test_energy_unknown_neutral():
    assert energy_fit(None, 7.0) == ("énergie n/a", 0.5)


def test_tag_match_bonus():
    assert tag_bonus("Peak", "Dark", "Peak", "Dark")[1] == 1.0
    assert tag_bonus("Warm-up", None, "Peak", None)[1] == 0.0
    assert tag_bonus(None, None, "Peak", "Dark") == ("ambiance n/a", 0.5)
    assert tag_bonus("Peak", "Dark", None, None) == ("ambiance n/a", 0.5)
