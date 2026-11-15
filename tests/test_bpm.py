from setbuilder.bpm import bpm_compat


def test_identical_bpm_perfect():
    label, s = bpm_compat(128.0, 128.0)
    assert s == 1.0 and "0" in label


def test_within_tolerance_high():
    assert bpm_compat(128.0, 131.0)[1] > 0.8


def test_beyond_tolerance_penalised():
    assert bpm_compat(128.0, 150.0)[1] < 0.3


def test_half_double_time_recognised():
    label, s = bpm_compat(128.0, 64.0)
    assert s > 0.8 and ("½" in label or "x2" in label)


def test_unknown_bpm_neutral():
    assert bpm_compat(None, 128.0) == ("BPM inconnu", 0.5)
    assert bpm_compat(128.0, None) == ("BPM inconnu", 0.5)
