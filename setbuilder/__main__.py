"""CLI : python -m setbuilder sync | analyze"""

import argparse
import subprocess
import sys
from pathlib import Path

from setbuilder.cache import open_cache
from setbuilder.rbread import read_library
from setbuilder.sync import sync

DEFAULT_CACHE = "setbuilder.db"


def rekordbox_running() -> bool:
    """True si le process Rekordbox tourne (pgrep -xi rekordbox, insensible à la casse)."""
    result = subprocess.run(["pgrep", "-xi", "rekordbox"], capture_output=True)
    return result.returncode == 0


def build_real_analyzers():
    """Câble les vrais modèles (extra `analysis`). Imports tardifs : modèles lourds."""
    from setbuilder.analyze import Analyzers
    from setbuilder.essentia_analyze import analyze_essentia
    from setbuilder.muq_analyze import analyze_muq

    return Analyzers(essentia=analyze_essentia, muq=analyze_muq)


def _cmd_analyze(args) -> int:
    from setbuilder.analyze import run_analyze
    from setbuilder.errors import AnalysisUnavailableError

    def progress(i, total, st):
        if i % 25 == 0 or i == total:
            print(f"[{i}/{total}] analysés={st.analyzed} sautés={st.skipped} "
                  f"introuvables={st.missing} échecs={st.failed}", flush=True)

    cache = open_cache(str(Path(args.cache)))
    try:
        stats = run_analyze(cache, analyzers=build_real_analyzers(), progress=progress)
    except AnalysisUnavailableError as e:
        print(f"Analyse impossible : {e}", file=sys.stderr)
        return 2
    finally:
        cache.close()
    print(f"analyze OK : {stats.analyzed} analysés, {stats.skipped} déjà à jour, "
          f"{stats.missing} fichiers introuvables, {stats.failed} échecs")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="setbuilder")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sync", help="Synchronise la librairie Rekordbox vers le cache local")
    p.add_argument("--cache", default=DEFAULT_CACHE, help="chemin du cache SQLite")
    a = sub.add_parser("analyze", help="Analyse audio (Essentia + MuQ + UMAP), incrémentale")
    a.add_argument("--cache", default=DEFAULT_CACHE, help="chemin du cache SQLite")
    args = parser.parse_args(argv)

    if rekordbox_running():
        print("Rekordbox est ouvert : ferme-le avant de lancer cette commande "
              "(master.db ne doit pas être lu pendant qu'il tourne, et l'analyse est lourde).",
              file=sys.stderr)
        return 1

    if args.command == "analyze":
        return _cmd_analyze(args)

    from pyrekordbox import Rekordbox6Database  # import tardif : dépendance optionnelle

    db = Rekordbox6Database()  # lecture seule : on n'appelle jamais commit()
    try:
        cache = open_cache(str(Path(args.cache)))
        stats = sync(read_library(db), cache)
    finally:
        db.close()
    print(f"sync OK : {stats.inserted} insérés, {stats.updated} mis à jour, "
          f"{stats.missing_files} fichiers introuvables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
