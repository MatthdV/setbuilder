"""Persistance des sets dans setbuilder.db (tables `sets` + `set_slots`).

Jamais de master.db ici. Un set = un mode (durée OU nombre), une cible, une
courbe d'énergie, et une liste ordonnée de slots (vides ou remplis).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

_MODES = {"duration", "count"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sets (
    set_id           TEXT PRIMARY KEY,
    name             TEXT,
    mode             TEXT,
    target           REAL,
    curve_json       TEXT,
    analysis_version TEXT,
    created_at       TEXT
);
CREATE TABLE IF NOT EXISTS set_slots (
    set_id     TEXT,
    position   INTEGER,
    content_id TEXT,
    is_anchor  INTEGER DEFAULT 0,
    is_forced  INTEGER DEFAULT 0,
    PRIMARY KEY (set_id, position)
);
"""


@dataclass
class Slot:
    position: int
    content_id: str | None
    is_anchor: bool
    is_forced: bool


@dataclass
class SetRecord:
    set_id: str
    name: str
    mode: str
    target: float
    curve_points: list[tuple[float, float]]
    analysis_version: str
    slots: list[Slot]


def open_sets(cache: sqlite3.Connection) -> None:
    cache.executescript(_SCHEMA)
    cache.commit()


def create_set(
    cache: sqlite3.Connection,
    name: str,
    mode: str,
    target: float,
    curve_points: list[tuple[float, float]],
    analysis_version: str,
    *,
    n_slots: int,
) -> str:
    if mode not in _MODES:
        raise ValueError(f"mode invalide : {mode!r} (attendu : {sorted(_MODES)})")
    set_id = uuid4().hex
    cache.execute(
        "INSERT INTO sets (set_id, name, mode, target, curve_json, analysis_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (set_id, name, mode, float(target), json.dumps(curve_points), analysis_version,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    cache.executemany(
        "INSERT INTO set_slots (set_id, position, content_id) VALUES (?, ?, NULL)",
        [(set_id, i) for i in range(n_slots)],
    )
    cache.commit()
    return set_id


def get_set(cache: sqlite3.Connection, set_id: str) -> SetRecord | None:
    row = cache.execute(
        "SELECT name, mode, target, curve_json, analysis_version FROM sets WHERE set_id = ?",
        (set_id,),
    ).fetchone()
    if row is None:
        return None
    name, mode, target, curve_json, analysis_version = row
    slot_rows = cache.execute(
        "SELECT position, content_id, is_anchor, is_forced FROM set_slots "
        "WHERE set_id = ? ORDER BY position",
        (set_id,),
    ).fetchall()
    slots = [Slot(pos, cid, bool(anchor), bool(forced)) for pos, cid, anchor, forced in slot_rows]
    points = [tuple(p) for p in json.loads(curve_json)]
    return SetRecord(set_id, name, mode, target, points, analysis_version, slots)


def list_sets(cache: sqlite3.Connection) -> list[SetRecord]:
    ids = [r[0] for r in cache.execute("SELECT set_id FROM sets ORDER BY created_at").fetchall()]
    return [get_set(cache, sid) for sid in ids]


def delete_set(cache: sqlite3.Connection, set_id: str) -> None:
    cache.execute("DELETE FROM set_slots WHERE set_id = ?", (set_id,))
    cache.execute("DELETE FROM sets WHERE set_id = ?", (set_id,))
    cache.commit()


def place_track(
    cache: sqlite3.Connection,
    set_id: str,
    position: int,
    content_id: str,
    *,
    is_anchor: bool = False,
    is_forced: bool = False,
) -> None:
    cache.execute(
        "UPDATE set_slots SET content_id = ?, is_anchor = ?, is_forced = ? "
        "WHERE set_id = ? AND position = ?",
        (content_id, int(is_anchor), int(is_forced), set_id, position),
    )
    cache.commit()


def clear_slot(cache: sqlite3.Connection, set_id: str, position: int) -> None:
    cache.execute(
        "UPDATE set_slots SET content_id = NULL, is_anchor = 0, is_forced = 0 "
        "WHERE set_id = ? AND position = ?",
        (set_id, position),
    )
    cache.commit()
