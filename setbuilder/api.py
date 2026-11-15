"""API FastAPI locale du set builder.

Mono-poste, pas d'auth, CORS ouvert pour le front local (plan 5). Toutes les
routes délèguent aux couches métier (sets_repo, suggest, impact) et lisent
`setbuilder.db` ; jamais master.db.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

from setbuilder.export import backup_db, export_set
from setbuilder.features_cache import open_features
from setbuilder.impact import ImpactReport, forced_impact
from setbuilder.scoring import Candidate, ScoreBreakdown
from setbuilder.sets_repo import (
    SetRecord,
    clear_slot,
    create_set,
    delete_set,
    get_set,
    list_sets,
    open_sets,
    place_track,
)
from setbuilder.slot_context import build_slot_context, candidates_by_id
from setbuilder.suggest import suggestions_for_slot
from setbuilder.timeline import slot_start_times


class ForceBody(BaseModel):
    content_id: str


def _serialize_breakdown(b: ScoreBreakdown) -> dict:
    return {"content_id": b.content_id, "score": b.score,
            "dimensions": {k: [label, score] for k, (label, score) in b.dimensions.items()}}


def _serialize_impact(r: ImpactReport) -> dict:
    return {"energy": list(r.energy), "key_prev": list(r.key_prev),
            "key_next": list(r.key_next), "bpm_prev": list(r.bpm_prev),
            "warnings": r.warnings}


def _next_filled(rec: SetRecord, pos: int, by_id: dict[str, Candidate]) -> Candidate | None:
    for s in rec.slots[pos + 1:]:
        if s.content_id and s.content_id in by_id:
            return by_id[s.content_id]
    return None


class SetCreate(BaseModel):
    name: str
    mode: str
    target: float
    curve_points: list[tuple[float, float]]
    n_slots: int
    analysis_version: str = "av1"


class SlotUpdate(BaseModel):
    content_id: str
    is_anchor: bool = False
    is_forced: bool = False


def _durations(conn: sqlite3.Connection, rec: SetRecord) -> list[float | None]:
    rows = conn.execute("SELECT content_id, duration_s FROM tracks").fetchall()
    by_id = {cid: dur for cid, dur in rows}
    return [by_id.get(s.content_id) if s.content_id else None for s in rec.slots]


def _serialize_set(conn: sqlite3.Connection, rec: SetRecord) -> dict:
    starts = slot_start_times(_durations(conn, rec))
    return {
        "set_id": rec.set_id, "name": rec.name, "mode": rec.mode, "target": rec.target,
        "curve_points": [list(p) for p in rec.curve_points],
        "analysis_version": rec.analysis_version,
        "slots": [
            {"position": s.position, "content_id": s.content_id, "is_anchor": s.is_anchor,
             "is_forced": s.is_forced, "start_time_s": starts[i]}
            for i, s in enumerate(rec.slots)
        ],
    }


def _require_set(conn: sqlite3.Connection, set_id: str) -> SetRecord:
    rec = get_set(conn, set_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="set introuvable")
    return rec


def _default_rb_provider():
    """Localise la base Rekordbox SANS l'ouvrir (extra `rekordbox`).

    Retourne (db_directory, open_db) : le backup se fait sur `db_directory`
    AVANT que `open_db()` ne construise la base — aucune ouverture de la vraie
    base avant le backup. Import paresseux : ImportError -> l'endpoint 503.
    """
    from pyrekordbox import Rekordbox6Database  # noqa: PLC0415
    from pyrekordbox.config import get_config  # noqa: PLC0415

    db_dir = get_config("rekordbox6", "db_dir")
    if not db_dir:
        db_dir = Path.home() / "Library" / "Pioneer" / "rekordbox"
    return str(db_dir), Rekordbox6Database


def _is_lock_error(exc: Exception) -> bool:
    return "lock" in str(exc).lower()


def create_app(db_path: str, *, rb_provider=None) -> FastAPI:
    rb_provider = rb_provider or _default_rb_provider
    app = FastAPI(title="setbuilder")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # Garantit que les tables du moteur existent, même sur une base ouverte
    # directement (les tables `tracks` viennent de cache.open_cache côté lib).
    open_features(conn)  # features + galaxy
    open_sets(conn)      # sets + set_slots
    app.state.conn = conn

    # Frontend statique (plan 5) : index.html a la racine, assets sous /static.
    if _WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_WEB_DIR)), name="static")

        @app.get("/")
        def index():
            return FileResponse(str(_WEB_DIR / "index.html"))

    @app.get("/library")
    def library():
        rows = conn.execute(
            "SELECT t.content_id, t.title, t.artist, t.bpm, t.camelot, t.genre, t.duration_s, "
            "f.energy_score, f.top_genre "
            "FROM tracks t LEFT JOIN features f ON f.content_id = t.content_id "
            "ORDER BY t.artist, t.title"
        ).fetchall()
        cols = ["content_id", "title", "artist", "bpm", "camelot", "genre", "duration_s",
                "energy_score", "top_genre"]
        return [dict(zip(cols, r)) for r in rows]

    @app.get("/galaxy")
    def galaxy():
        rows = conn.execute("SELECT content_id, umap_x, umap_y FROM galaxy").fetchall()
        return [{"content_id": c, "umap_x": x, "umap_y": y} for c, x, y in rows]

    @app.post("/sets")
    def post_set(body: SetCreate):
        try:
            sid = create_set(conn, body.name, body.mode, body.target, body.curve_points,
                             body.analysis_version, n_slots=body.n_slots)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return {"set_id": sid}

    @app.get("/sets")
    def get_sets():
        return [_serialize_set(conn, r) for r in list_sets(conn)]

    @app.get("/sets/{set_id}")
    def get_one_set(set_id: str):
        return _serialize_set(conn, _require_set(conn, set_id))

    @app.delete("/sets/{set_id}")
    def del_set(set_id: str):
        _require_set(conn, set_id)
        delete_set(conn, set_id)
        return {"ok": True}

    @app.put("/sets/{set_id}/slots/{pos}")
    def put_slot(set_id: str, pos: int, body: SlotUpdate):
        rec = _require_set(conn, set_id)
        if not 0 <= pos < len(rec.slots):
            raise HTTPException(status_code=404, detail="slot hors bornes")
        place_track(conn, set_id, pos, body.content_id,
                    is_anchor=body.is_anchor, is_forced=body.is_forced)
        return _serialize_set(conn, _require_set(conn, set_id))["slots"][pos]

    @app.delete("/sets/{set_id}/slots/{pos}")
    def del_slot(set_id: str, pos: int):
        rec = _require_set(conn, set_id)
        if not 0 <= pos < len(rec.slots):
            raise HTTPException(status_code=404, detail="slot hors bornes")
        clear_slot(conn, set_id, pos)
        return {"ok": True}

    @app.get("/sets/{set_id}/slots/{pos}/suggestions")
    def slot_suggestions(set_id: str, pos: int, limit: int = 20):
        rec = _require_set(conn, set_id)
        if not 0 <= pos < len(rec.slots):
            raise HTTPException(status_code=404, detail="slot hors bornes")
        return [_serialize_breakdown(b) for b in suggestions_for_slot(conn, rec, pos, limit=limit)]

    @app.post("/sets/{set_id}/slots/{pos}/force")
    def force_slot(set_id: str, pos: int, body: ForceBody):
        rec = _require_set(conn, set_id)
        if not 0 <= pos < len(rec.slots):
            raise HTTPException(status_code=404, detail="slot hors bornes")
        by_id = candidates_by_id(conn, rec.analysis_version)
        forced = by_id.get(body.content_id)
        if forced is None:
            raise HTTPException(status_code=404, detail="morceau introuvable dans la lib")
        durations = _durations(conn, rec)
        ctx = build_slot_context(rec, pos, by_id, durations)
        next_ = _next_filled(rec, pos, by_id)
        report = forced_impact(forced, ctx.prev, next_, ctx.target_energy)
        place_track(conn, set_id, pos, body.content_id, is_forced=True)
        slot = _serialize_set(conn, _require_set(conn, set_id))["slots"][pos]
        return {"slot": slot, "impact": _serialize_impact(report)}

    @app.post("/sets/{set_id}/export")
    def export_rekordbox(set_id: str):
        rec = _require_set(conn, set_id)
        content_ids = [s.content_id for s in rec.slots if s.content_id]
        if not content_ids:
            raise HTTPException(status_code=400, detail="set vide : aucun morceau a exporter")

        try:
            db_dir, open_db = rb_provider()
        except ImportError as e:
            raise HTTPException(
                status_code=503,
                detail="extra `rekordbox` absent : `uv sync --extra rekordbox`",
            ) from e

        # Backup AVANT toute ouverture/ecriture de la base Rekordbox.
        try:
            backup_dir = backup_db(db_dir, "backups")
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=500, detail=f"base Rekordbox introuvable : {e}"
            ) from e

        # Ouverture puis export seulement apres le backup. Un verrou (Rekordbox
        # ouvert) -> 409 ; toute autre erreur -> 500 (pas de 409 trompeur).
        try:
            db = open_db()
            result = export_set(db, rec.name, content_ids)
        except HTTPException:
            raise
        except Exception as e:
            if _is_lock_error(e):
                raise HTTPException(
                    status_code=409, detail="ferme Rekordbox et reessaie"
                ) from e
            raise HTTPException(status_code=500, detail=f"echec export : {e}") from e
        result["backup"] = backup_dir
        return result

    return app
