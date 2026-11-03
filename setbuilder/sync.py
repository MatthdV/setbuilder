"""Synchronisation idempotente Track -> cache local (upsert par content_id)."""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from setbuilder.files import resolve_file
from setbuilder.rbread import Track

_COLUMNS = (
    "title", "artist", "album", "bpm", "camelot", "rb_key", "moment", "ambiance",
    "genre", "file_path", "file_status", "duration_s", "has_cues", "has_phrases",
)
_UPSERT = (
    f"INSERT INTO tracks (content_id, {', '.join(_COLUMNS)}, updated_at) "
    f"VALUES (:content_id, {', '.join(':' + c for c in _COLUMNS)}, :updated_at) "
    "ON CONFLICT(content_id) DO UPDATE SET "
    + ", ".join(f"{c}=excluded.{c}" for c in (*_COLUMNS, "updated_at"))
)


@dataclass
class SyncStats:
    inserted: int = 0
    updated: int = 0
    missing_files: int = 0


def sync(tracks: Iterable[Track], cache: sqlite3.Connection) -> SyncStats:
    """Upsert les tracks ; `updated` ne compte que les lignes dont une valeur a changé."""
    stats = SyncStats()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    select = f"SELECT {', '.join(_COLUMNS)} FROM tracks WHERE content_id = ?"
    for track in tracks:
        if track.file_path:
            resolved, status = resolve_file(track.file_path)
        else:
            resolved, status = None, "missing"
        params = {c: getattr(track, c, None) for c in _COLUMNS}
        params.update(
            content_id=track.content_id,
            file_path=resolved or track.file_path,
            file_status=status,
            updated_at=now,
        )
        existing = cache.execute(select, (track.content_id,)).fetchone()
        if existing is None:
            stats.inserted += 1
        elif existing != tuple(params[c] for c in _COLUMNS):
            stats.updated += 1
        if status == "missing":
            stats.missing_files += 1
        cache.execute(_UPSERT, params)
    cache.commit()
    return stats
