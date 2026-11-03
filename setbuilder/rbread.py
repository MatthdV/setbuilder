"""Lecture de la librairie Rekordbox (pyrekordbox) vers des dataclasses."""
from collections.abc import Iterator
from dataclasses import dataclass

from setbuilder.camelot import to_camelot


@dataclass
class Track:
    content_id: str
    title: str | None
    artist: str | None
    album: str | None
    bpm: float | None
    camelot: str | None
    rb_key: str | None
    moment: str | None
    ambiance: str | None
    genre: str | None
    file_path: str | None
    duration_s: int | None
    has_cues: int
    has_phrases: int


def _get(obj, *names):
    """Premier attribut non-None parmi names, sinon None."""
    for name in names:
        value = getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _raw_key(row) -> str | None:
    direct = _get(row, "KeyName")
    if direct is not None:
        return str(direct)
    scale = _get(getattr(row, "Key", None), "ScaleName")
    if scale is not None:
        return str(scale)
    return None


def _my_tags(row) -> dict[str, str]:
    """Renvoie {catégorie en minuscules: nom du tag} (premier tag par catégorie)."""
    found: dict[str, str] = {}
    for link in getattr(row, "MyTags", None) or []:
        tag = getattr(link, "MyTag", link)
        name = _get(tag, "Name")
        category = _get(getattr(tag, "Parent", None), "Name")
        if name is not None and category is not None:
            found.setdefault(str(category).lower(), str(name))
    return found


def map_content(row) -> Track:
    bpm_raw = _get(row, "BPM")
    rb_key = _raw_key(row)
    tags = _my_tags(row)
    length = _get(row, "Length")
    return Track(
        content_id=str(row.ID),
        title=_get(row, "Title"),
        artist=_get(row, "ArtistName"),
        album=_get(row, "AlbumName"),
        bpm=bpm_raw / 100 if bpm_raw else None,
        camelot=to_camelot(rb_key),
        rb_key=rb_key,
        moment=tags.get("moment"),
        ambiance=tags.get("ambiance"),
        genre=_get(row, "GenreName", "Genre"),
        file_path=_get(row, "FolderPath"),
        duration_s=int(length) if length else None,
        has_cues=1 if getattr(row, "Cues", None) else 0,
        has_phrases=1 if getattr(row, "Phrases", None) else 0,
    )


def read_library(db) -> Iterator[Track]:
    for row in db.get_content():
        yield map_content(row)
