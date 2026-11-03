"""CLI : python -m setbuilder sync"""

import argparse
import subprocess
import sys
from pathlib import Path

from setbuilder.cache import open_cache
from setbuilder.rbread import read_library
from setbuilder.sync import sync

DEFAULT_CACHE = "setbuilder.db"


def rekordbox_running() -> bool:
    """True si le process Rekordbox tourne (pgrep -x rekordbox)."""
    result = subprocess.run(["pgrep", "-xi", "rekordbox"], capture_output=True)
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="setbuilder")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sync", help="Synchronise la librairie Rekordbox vers le cache local")
    p.add_argument("--cache", default=DEFAULT_CACHE, help="chemin du cache SQLite")
    args = parser.parse_args(argv)

    if rekordbox_running():
        print("Rekordbox est ouvert : ferme-le avant de synchroniser "
              "(master.db ne doit pas être lu pendant qu'il tourne).", file=sys.stderr)
        return 1

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
