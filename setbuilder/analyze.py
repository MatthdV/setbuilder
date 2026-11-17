"""Batch d'analyse incrémental : features Essentia + embedding MuQ + carte UMAP."""

import sqlite3
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from setbuilder.audio import load_audio_16k_mono
from setbuilder.energy import ENERGY_FORMULA_VERSION
from setbuilder.errors import AnalysisUnavailableError
from setbuilder.essentia_analyze import to_cache_dict
from setbuilder.features_cache import has_features, open_features, record_failure, upsert_features
from setbuilder.galaxy import UMAP_VERSION, fit_umap

# change si un modèle ou la formule change -> force la ré-analyse
ANALYSIS_VERSION = f"effnet-discogs400+muq-large-msd-iter+{ENERGY_FORMULA_VERSION}"


@dataclass
class Analyzers:
    """Briques d'analyse injectables (les vraies sont câblées par le CLI)."""

    essentia: Callable
    muq: Callable
    load_audio: Callable = load_audio_16k_mono


@dataclass
class AnalyzeStats:
    analyzed: int = 0
    skipped: int = 0
    missing: int = 0
    failed: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (content_id, message)


# Règle unique "candidat analysable" partagée (P2-5) : un track est analysable
# s'il a un file_path utilisable. count_pending la réutilise pour le dénominateur
# du front ; run_analyze applique le MÊME test (`if file_path`) track par track.
_ANALYZABLE_WHERE = "file_path IS NOT NULL AND file_path != ''"


def count_pending(
    cache: sqlite3.Connection, analysis_version: str = ANALYSIS_VERSION
) -> tuple[int, int]:
    """(pending, total) des tracks analysables.

    total = tracks avec un file_path utilisable. pending = ceux-là sans features
    à `analysis_version`. Même filtre que la sélection de candidats de
    run_analyze, pour que la barre de progression atteigne bien 0.
    """
    open_features(cache)
    total = cache.execute(
        f"SELECT COUNT(*) FROM tracks WHERE {_ANALYZABLE_WHERE}"
    ).fetchone()[0]
    pending = cache.execute(
        f"SELECT COUNT(*) FROM tracks t WHERE {_ANALYZABLE_WHERE} "
        "AND NOT EXISTS (SELECT 1 FROM features f "
        "WHERE f.content_id = t.content_id AND f.analysis_version = ?) "
        "AND NOT EXISTS (SELECT 1 FROM analyze_failures x "
        "WHERE x.content_id = t.content_id AND x.analysis_version = ?)",
        (analysis_version, analysis_version),
    ).fetchone()[0]
    return pending, total


def count_failed(cache: sqlite3.Connection, analysis_version: str = ANALYSIS_VERSION) -> int:
    open_features(cache)
    return cache.execute(
        "SELECT COUNT(*) FROM analyze_failures x JOIN tracks t ON t.content_id = x.content_id "
        "WHERE x.analysis_version = ?", (analysis_version,)).fetchone()[0]


def run_analyze(
    cache: sqlite3.Connection,
    *,
    analyzers: Analyzers,
    analysis_version: str = ANALYSIS_VERSION,
    progress: Callable[[int, int, AnalyzeStats], None] | None = None,
) -> AnalyzeStats:
    """Analyse les tracks sans features à jour ; puis recalcule la carte UMAP si besoin.

    Un track dont le fichier est introuvable ou dont l'analyse échoue n'interrompt pas le batch.
    Seule `AnalysisUnavailableError` (modèles indisponibles) l'arrête.
    """
    open_features(cache)
    # Même filtre que count_pending (P2-5) : seuls les tracks analysables entrent
    # dans le batch, pour que son `total` (progress) == /analyze/pending.total.
    # Un file_path nul/vide n'est pas un candidat (pas compté `missing`).
    rows = cache.execute(
        f"SELECT content_id, file_path FROM tracks t WHERE {_ANALYZABLE_WHERE} "
        "AND NOT EXISTS (SELECT 1 FROM analyze_failures x "
        "WHERE x.content_id = t.content_id AND x.analysis_version = ?) ORDER BY content_id",
        (analysis_version,),
    ).fetchall()
    stats = AnalyzeStats()

    for i, (content_id, file_path) in enumerate(rows, 1):
        if has_features(cache, content_id, analysis_version):
            stats.skipped += 1
        else:
            audio = analyzers.load_audio(file_path) if file_path else None
            if audio is None or len(audio) == 0:
                stats.missing += 1
            else:
                try:
                    feats = analyzers.essentia(audio)
                    emb = analyzers.muq(audio)
                    if emb is None or not np.isfinite(emb).all():
                        raise ValueError("embedding MuQ vide ou non fini")
                    upsert_features(cache, content_id, {
                        **to_cache_dict(feats),
                        "muq_embedding": emb,
                        "analysis_version": analysis_version,
                    })
                    stats.analyzed += 1
                except AnalysisUnavailableError:
                    raise
                except Exception as e:  # noqa: BLE001 - un track KO ne doit pas tuer le batch
                    stats.failed += 1
                    stats.failures.append((content_id, str(e)[:200]))
                    record_failure(cache, content_id, analysis_version, str(e))
        if progress:
            progress(i, len(rows), stats)

    _refresh_galaxy(cache, analysis_version, force=stats.analyzed > 0)
    return stats


def _refresh_galaxy(cache: sqlite3.Connection, analysis_version: str, *, force: bool) -> None:
    ids, embs = [], []
    for cid, blob in cache.execute(
        "SELECT content_id, muq_embedding FROM features "
        "WHERE analysis_version = ? AND muq_embedding IS NOT NULL ORDER BY content_id",
        (analysis_version,),
    ):
        ids.append(cid)
        embs.append(np.frombuffer(blob, dtype=np.float32))
    id_set = set(ids)

    # Purge les coords qui n'ont plus d'embedding à la version courante (bump de
    # version, embedding perdu) : sinon /galaxy sert des coords périmées. La purge
    # n'est PAS commit ici : elle doit l'être avec le recompute (transaction unique),
    # sinon /galaxy pourrait servir un état partiel si fit_umap échoue.
    existing = {r[0] for r in cache.execute("SELECT content_id FROM galaxy")}
    orphans = existing - id_set
    if orphans:
        cache.executemany("DELETE FROM galaxy WHERE content_id = ?", [(o,) for o in orphans])

    if not ids:
        cache.commit()  # galaxy vidée : rien à recomputer, on persiste la purge seule
        return
    # Resync si forcé, OU si l'ensemble des coords présentes ne couvre pas déjà
    # exactement les ids courants (un simple compte égal ne suffit pas : des ids
    # différents peuvent coïncider en nombre après un changement de version).
    # Lecture dans la même connexion : voit les DELETE non encore commit.
    have_ids = {r[0] for r in cache.execute(
        "SELECT content_id FROM galaxy WHERE umap_version = ?", (UMAP_VERSION,))}
    if not force and have_ids == id_set:
        cache.commit()  # persiste la purge éventuelle ; no-op si aucun orphelin
        return
    try:
        coords = fit_umap(np.stack(embs))
    except Exception:
        cache.rollback()  # ne pas laisser la purge visible sans coords recalculées
        raise
    cache.executemany(
        "INSERT INTO galaxy (content_id, umap_x, umap_y, umap_version) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(content_id) DO UPDATE SET umap_x=excluded.umap_x, umap_y=excluded.umap_y, "
        "umap_version=excluded.umap_version",
        [(cid, float(x), float(y), UMAP_VERSION) for cid, (x, y) in zip(ids, coords)],
    )
    cache.commit()  # purge + coords : un seul commit atomique
