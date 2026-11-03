import pytest

from setbuilder.camelot import to_camelot


@pytest.mark.parametrize(
    "rb_key, expected",
    [
        # Brief-pinned assertions
        ("Abm", "1A"),
        ("B", "1B"),
        ("Em", "9A"),
        ("G", "9B"),
        ("", None),
        (None, None),
        ("??", None),
        # Major keys (B side)
        ("C", "8B"),
        ("G", "9B"),
        ("D", "10B"),
        ("A", "11B"),
        ("E", "12B"),
        ("B", "1B"),
        ("F#", "2B"),
        ("Gb", "2B"),
        ("Db", "3B"),
        ("C#", "3B"),
        ("Ab", "4B"),
        ("Eb", "5B"),
        ("D#", "5B"),
        ("Bb", "6B"),
        ("A#", "6B"),
        ("F", "7B"),
        # Minor keys (A side)
        ("Am", "8A"),
        ("Em", "9A"),
        ("Bm", "10A"),
        ("F#m", "11A"),
        ("Gbm", "11A"),
        ("C#m", "12A"),
        ("Dbm", "12A"),
        ("G#m", "1A"),
        ("Abm", "1A"),
        ("D#m", "2A"),
        ("Ebm", "2A"),
        ("Bbm", "3A"),
        ("A#m", "3A"),
        ("Fm", "4A"),
        ("Cm", "5A"),
        ("Gm", "6A"),
        ("Dm", "7A"),
    ],
)
def test_to_camelot(rb_key, expected):
    assert to_camelot(rb_key) == expected


@pytest.mark.parametrize("rb_key", ["H", "Xm", "Cmaj7", "  ", "C#b", "12A"])
def test_to_camelot_unknown_returns_none(rb_key):
    assert to_camelot(rb_key) is None
