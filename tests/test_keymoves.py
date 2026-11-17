"""La table de mixage (image de référence) + son usage dans le scoring et les suggestions."""
import numpy as np
import pytest

from setbuilder.impact import forced_impact
from setbuilder.keymoves import key_move, move_score, moves_from
from setbuilder.scoring import Candidate, SlotContext, score_candidate
from setbuilder.suggest import diversify

# (perfect, +, ++, +++, -, --, ---, mood) ; entre parenthèses de la table = `weak`
REF = {
    "1A": ("1A 12B", "1B 2A", "10A", "3A (8A)", "12A", "4A", "11A (6A)", "4B"),
    "5A": ("5A 4B", "5B 6A", "2A", "7A (12A)", "4A", "8A", "3A (10A)", "8B"),
    "12A": ("12A 11B", "12B 1A", "9A", "2A (7A)", "11A", "3A", "10A (5A)", "3B"),
    "1B": ("1B 2A", "2B", "10B", "3B (8B)", "1A 12B", "4B", "11B (6B)", "10A"),
    "4B": ("4B 5A", "5B", "1B", "6B (11B)", "4A 3B", "7B", "2B (9B)", "1A"),
    "12B": ("12B 1A", "1B", "9B", "2B (7B)", "12A 11B", "3B", "10B (5B)", "9A"),
}
COLS = [("perfect", 0), ("boost", 1), ("boost", 2), ("boost", 3),
        ("drop", 1), ("drop", 2), ("drop", 3), ("mood", 0)]


def _expected(row):
    out = {}
    for (cat, tier), cell in zip(COLS, row):
        for tok in cell.replace("(", "").replace(")", "").split():
            out.setdefault(tok, (cat, tier, "(" in cell and cell.endswith(f"({tok})") or f"({tok})" in cell))
    return out


@pytest.mark.parametrize("key", REF)
def test_moves_match_reference_table(key):
    got = {k: (m.category, m.tier, m.weak) for k, m in moves_from(key).items()}
    assert got == _expected(REF[key])


def test_unknown_key_has_no_moves():
    assert moves_from(None) == {} and moves_from("zz") == {}
    assert key_move("8A", None) is None


def test_boost_favoured_when_energy_must_rise_and_penalised_when_it_falls():
    boost = key_move("8A", "9A")  # + (boost)
    assert move_score(boost, +2.0) > move_score(boost, 0.0) > move_score(boost, -2.0)
    drop = key_move("8A", "7A")
    assert move_score(drop, -2.0) > move_score(drop, 0.0) > move_score(drop, +2.0)


def _c(cid, key, energy=7, bpm=128.0):
    return Candidate(content_id=cid, title=cid, artist=None, bpm=bpm, camelot=key, energy=energy,
                     moment=None, ambiance=None, embedding=None)


def test_scoring_uses_table_and_direction():
    prev = _c("p", "1A", energy=5)
    up = SlotContext(prev=prev, target_energy=8.0)
    down = SlotContext(prev=prev, target_energy=2.0)
    cand = _c("c", "10A")  # ++ boost : hors ±1 classique (aurait été un clash)
    s_up = score_candidate(cand, up).dimensions["key"]
    s_down = score_candidate(cand, down).dimensions["key"]
    assert s_up[0] == "key boost ++" and s_up[1] > 0.7 > s_down[1]
    assert score_candidate(_c("s", "1A"), up).dimensions["key"][1] == 1.0  # même clé inchangé


def test_forced_impact_does_not_call_table_moves_a_clash():
    prev = _c("p", "1A")
    rep = forced_impact(_c("f", "10A"), prev, None, 7.0)
    assert not any("key" in w for w in rep.warnings)


def test_suggestions_are_not_all_same_key():
    prev = _c("p", "8A", energy=5)
    pool = [_c(f"same{i}", "8A") for i in range(30)]
    pool += [_c(f"b{i}", "9A") for i in range(5)] + [_c(f"d{i}", "7A") for i in range(5)]
    pool += [_c(f"m{i}", "11B") for i in range(5)]
    by_id = {c.content_id: c for c in pool}
    ctx = SlotContext(prev=prev, target_energy=8.0)
    ranked = sorted((score_candidate(c, ctx) for c in pool), key=lambda b: (-b.score, b.content_id))
    # sans diversité : on ne verrait que des 8A
    assert {by_id[b.content_id].camelot for b in ranked[:15]} == {"8A"}
    out = diversify(ranked, prev, by_id, 3.0, 15)
    keys = [by_id[b.content_id].camelot for b in out]
    assert len(out) == 15 and {"8A", "9A", "7A", "11B"} <= set(keys)
    assert keys.count("9A") == 3  # énergie à monter : boosts favorisés, mais max 3 par clé exacte
    assert keys.count("8A") >= 4  # la même clé reste bien représentée
