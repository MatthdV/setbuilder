"""Conversion d'une clé musicale Rekordbox vers la notation Camelot.

Camelot : mineur = <n>A, majeur = <n>B. La roue suit les quintes.
Indexé par pitch class (C=0 … B=11).
"""

import re

_CAMELOT_RE = re.compile(r"^(?:[1-9]|1[0-2])[AB]$")
_NOTE_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ACCIDENTALS = {"#": 1, "♯": 1, "b": -1, "♭": -1}
_MAJOR_NUMBER = {0: 8, 7: 9, 2: 10, 9: 11, 4: 12, 11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7}
_MINOR_NUMBER = {9: 8, 4: 9, 11: 10, 6: 11, 1: 12, 8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7}
_MAJOR_SUFFIXES = ("", "maj", "major")
_MINOR_SUFFIXES = ("m", "min", "minor")


def _parse(rb_key: str) -> tuple[int, bool] | None:
    """Renvoie (pitch class, est_mineur) ou None si la clé n'est pas reconnue."""
    key = rb_key.strip()
    if not key or key[0].upper() not in _NOTE_SEMITONES:
        return None
    semitone = _NOTE_SEMITONES[key[0].upper()]
    rest = key[1:]
    if rest[:1] in _ACCIDENTALS:
        semitone += _ACCIDENTALS[rest[0]]
        rest = rest[1:]
    suffix = rest.lower()
    if suffix in _MAJOR_SUFFIXES:
        is_minor = False
    elif suffix in _MINOR_SUFFIXES:
        is_minor = True
    else:
        return None
    return semitone % 12, is_minor


def to_camelot(rb_key: str | None) -> str | None:
    """Convertit une clé Rekordbox (ex. "Abm", "B", "F#m") en Camelot ("1A", "1B").

    Renvoie None si la clé est vide, absente ou non reconnue.
    """
    if not rb_key:
        return None
    # Rekordbox peut déjà stocker la clé en Camelot ("7A") : on la renvoie telle quelle.
    if _CAMELOT_RE.match(rb_key.strip().upper()):
        return rb_key.strip().upper()
    parsed = _parse(rb_key)
    if parsed is None:
        return None
    pitch_class, is_minor = parsed
    if is_minor:
        return f"{_MINOR_NUMBER[pitch_class]}A"
    return f"{_MAJOR_NUMBER[pitch_class]}B"
