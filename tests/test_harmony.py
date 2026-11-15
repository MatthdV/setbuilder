from setbuilder.harmony import camelot_compat


def test_same_key_is_perfect():
    assert camelot_compat("8A", "8A") == ("key ✓ (même)", 1.0)


def test_adjacent_wheel():
    assert camelot_compat("8A", "9A")[1] == 0.9
    assert camelot_compat("12B", "1B")[1] == 0.9


def test_relative_major_minor():
    assert camelot_compat("8A", "8B")[1] == 0.85


def test_energy_boost_plus_two():
    assert camelot_compat("8A", "10A")[1] == 0.6


def test_incompatible():
    assert camelot_compat("8A", "3B")[1] == 0.0


def test_unknown_key_is_neutral():
    assert camelot_compat("8A", None) == ("key inconnue", 0.5)
    assert camelot_compat(None, "8A") == ("key inconnue", 0.5)
    assert camelot_compat("8A", "bogus") == ("key inconnue", 0.5)
