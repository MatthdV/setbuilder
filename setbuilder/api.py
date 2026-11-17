"""API FastAPI locale du set builder.

Mono-poste, pas d'auth, CORS ouvert pour le front local (plan 5). Toutes les
routes délèguent aux couches métier (sets_repo, suggest, impact) et lisent
`setbuilder.db` ; jamais master.db.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"

from setbuilder.analyze import ANALYSIS_VERSION, count_failed, count_pending
from setbuilder.analyze_job import (
    pid_alive,
    read_status,
    read_status_raw,
    status_path_for,
    write_status,
)
from setbuilder.analyze_launch import spawn_analyze
from setbuilder.cache import apply_pragmas, ensure_schema
from setbuilder.export import backup_db, export_set
from setbuilder.features_cache import open_features, resolve_analysis_version
from setbuilder.curve import PRESETS
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
    overwrite: bool = False


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


_Pt = tuple[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)],
            Annotated[float, Field(ge=0, le=10, allow_inf_nan=False)]]


class SetCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    mode: Literal["count", "duration"]
    target: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    curve_points: Annotated[list[_Pt], Field(min_length=1, max_length=64)] | None = None
    set_type: Literal["warmup", "main", "closing", "after"] | None = None
    n_slots: Annotated[int, Field(ge=1, le=200)]
    analysis_version: str = ANALYSIS_VERSION

    @model_validator(mode="after")
    def _curve_or_type(self):
        if self.curve_points is None and self.set_type is None:
            raise ValueError("set_type ou curve_points requis")
        if self.curve_points is None:
            self.curve_points = [tuple(p) for p in PRESETS[self.set_type]]
        return self


class SlotUpdate(BaseModel):
    content_id: str
    overwrite: bool = False
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
        "set_type": rec.set_type or "custom",
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
    rec.analysis_version = resolve_analysis_version(conn, rec.analysis_version)
    return rec


def _check_placement(rec: SetRecord, pos: int, content_id: str, overwrite: bool) -> None:
    """409 si le morceau est déjà dans un autre slot, ou si le slot cible est
    ancré/forcé et que l'écrasement n'est pas explicite."""
    for s in rec.slots:
        if s.content_id == content_id and s.position != pos:
            raise HTTPException(status_code=409, detail="duplicate_track")
    cur = rec.slots[pos]
    if cur.content_id and (cur.is_anchor or cur.is_forced) and cur.content_id != content_id and not overwrite:
        raise HTTPException(status_code=409, detail="slot_protected")


def _default_rb_provider():
    """Localise la base Rekordbox SANS l'ouvrir (extra `rekordbox`).

    Retourne (db_directory, open_db) : le backup se fait sur `db_directory`
    AVANT que `open_db()` ne construise la base — aucune ouverture de la vraie
    base avant le backup. Import paresseux : ImportError -> l'endpoint 503.
    """
    from pyrekordbox import Rekordbox6Database  # noqa: PLC0415
    from pyrekordbox.config import get_config  # noqa: PLC0415

    try:
        db_dir = get_config("rekordbox6", "db_dir")
    except Exception:  # KeyError si la config Rekordbox est absente
        db_dir = None
    if not db_dir:
        db_dir = Path.home() / "Library" / "Pioneer" / "rekordbox"
    return str(db_dir), Rekordbox6Database


def _is_lock_error(exc: Exception) -> bool:
    return "lock" in str(exc).lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_rekordbox_probe() -> bool:
    from setbuilder.__main__ import rekordbox_running  # import tardif : évite le poids au boot
    return rekordbox_running()


def create_app(db_path: str, *, rb_provider=None, analyze_launcher=None,
               rekordbox_probe=None) -> FastAPI:
    rb_provider = rb_provider or _default_rb_provider
    analyze_launcher = analyze_launcher or spawn_analyze
    rekordbox_probe = rekordbox_probe or _default_rekordbox_probe
    status_path = status_path_for(db_path)
    analyze_lock = threading.Lock()
    app = FastAPI(title="setbuilder")
    # Pas de CORS : le front est servi en même origine. Garde locale : l'Host doit être
    # loopback (anti DNS-rebinding) et un Origin éventuel doit l'être aussi (anti CSRF,
    # y compris les POST « simples » sans preflight comme POST /analyze).
    _LOCAL = {"127.0.0.1", "localhost", "::1", "testserver"}

    @app.middleware("http")
    async def _local_only(request, call_next):
        from urllib.parse import urlsplit  # noqa: PLC0415
        try:
            u = urlsplit("//" + (request.headers.get("host") or ""))
            u.port  # noqa: B018 - lève ValueError si le port est invalide
            host = u.hostname or ""
        except ValueError:
            host = ""
        origin = request.headers.get("origin")
        if host not in _LOCAL:
            return JSONResponse(status_code=403, content={"detail": "hôte non autorisé"})
        if origin and origin != "null":
            try:
                u = urlsplit(origin)
                u.port  # noqa: B018
                o_host = u.hostname or ""
            except ValueError:
                o_host = ""
            if o_host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
                return JSONResponse(status_code=403, content={"detail": "origine non autorisée"})
        elif origin == "null":
            return JSONResponse(status_code=403, content={"detail": "origine non autorisée"})
        return await call_next(request)
    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request, exc):
        # Sans `input` : un NaN/inf dans le corps ferait échouer la sérialisation (500).
        errs = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errs})

    conn = sqlite3.connect(db_path, check_same_thread=False)
    apply_pragmas(conn)  # WAL + busy_timeout : partage sûr du cache avec le sous-process d'analyse
    # Garantit que les tables du moteur existent, même sur une base ouverte
    # directement (les tables `tracks` viennent de cache.open_cache côté lib).
    ensure_schema(conn)  # tracks (DB neuve)
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
                             body.analysis_version, n_slots=body.n_slots, set_type=body.set_type)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return {"set_id": sid}

    @app.get("/sets")
    def get_sets():
        out = []
        for sid in [r[0] for r in conn.execute("SELECT set_id FROM sets ORDER BY created_at")]:
            try:
                out.append(_serialize_set(conn, _require_set(conn, sid)))
                json.dumps(out[-1], allow_nan=False)
            except Exception:
                if out and out[-1].get("set_id") != sid:
                    pass
                elif out:
                    out.pop()
                logging.getLogger(__name__).warning("set %s illisible, ignoré", sid)
        return out

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
        if conn.execute("SELECT 1 FROM tracks WHERE content_id = ?", (body.content_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="morceau introuvable dans la lib")
        _check_placement(rec, pos, body.content_id, body.overwrite)
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
    def slot_suggestions(set_id: str, pos: int, limit: int = Query(20, ge=1, le=100)):
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
        _check_placement(rec, pos, body.content_id, body.overwrite)
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
        # Fermeture systematique de la base dans finally : ne jamais retenir le
        # verrou sqlite apres la requete, meme sur echec (un handle ouvert
        # ferait echouer a tort l'export suivant). close() optionnel (duck-type).
        db = None
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
        finally:
            if db is not None:
                close = getattr(db, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass
        result["backup"] = backup_dir
        return result

    # --- Analyse pilotée depuis l'app (plan 6) ---------------------------------

    @app.get("/analyze/pending")
    def analyze_pending():
        pending, total = count_pending(conn)
        return {"pending": pending, "total": total, "failed": count_failed(conn)}

    @app.get("/analyze/status")
    def analyze_status():
        return read_status(status_path)  # jamais 500 ; idle/running/stale/done/error

    @app.post("/analyze")
    def analyze_start():
        with analyze_lock:  # sérialise check -> claim -> spawn -> CAS (uvicorn mono-worker)
            status = read_status(status_path)
            if status.get("state") == "running" and pid_alive(status.get("pid")):
                raise HTTPException(status_code=409, detail="analyse déjà en cours")
            if rekordbox_probe():
                raise HTTPException(
                    status_code=409, detail="ferme Rekordbox pour lancer l'analyse")
            pending, _ = count_pending(conn)
            # Claim AVANT le spawn : pid None, dérivé en `stale` tant que le pid n'est pas posé.
            write_status(status_path, {"state": "running", "pid": None, "i": 0,
                                       "total": pending, "started_at": _now()})
            pid = analyze_launcher(db_path, status_path)
            # CAS post-spawn : ne pose le pid que si la claim est intacte (brut, pas dérivé).
            raw = read_status_raw(status_path)
            if raw.get("state") == "running" and raw.get("pid") is None:
                raw = dict(raw)
                raw["pid"] = pid
                write_status(status_path, raw)
            return JSONResponse(status_code=202,
                                content={"pid": pid, "status_url": "/analyze/status"})

    return app
