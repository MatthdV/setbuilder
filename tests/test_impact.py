from setbuilder.impact import forced_impact
from setbuilder.scoring import Candidate


def _c(cid, bpm, cam, e):
    return Candidate(cid, cid, "x", bpm, cam, e, None, None, None)


def test_clash_and_energy_dip_warned():
    forced = _c("f", 150.0, "3B", 2)
    prev = _c("p", 128.0, "8A", 7)
    rep = forced_impact(forced, prev, None, target_energy=8.0)
    assert rep.key_prev[1] == 0.0
    assert rep.energy[1] < 0.4
    assert any("key" in w.lower() for w in rep.warnings)
    assert any("énergie" in w.lower() for w in rep.warnings)


def test_no_neighbour_is_na_not_error():
    rep = forced_impact(_c("f", 128.0, "8A", 7), None, None, target_energy=7.0)
    assert rep.key_prev == ("key inconnue", 0.5)
    assert rep.warnings == []


def test_missing_features_na():
    forced = Candidate("f", "f", "x", None, None, None, None, None, None)
    rep = forced_impact(forced, _c("p", 128.0, "8A", 7), None, target_energy=7.0)
    assert rep.energy == ("énergie n/a", 0.5)


def test_bpm_jump_warned():
    forced = _c("f", 170.0, "8A", 7)
    prev = _c("p", 120.0, "8A", 7)
    rep = forced_impact(forced, prev, None, target_energy=7.0)
    assert any("bpm" in w.lower() for w in rep.warnings)
