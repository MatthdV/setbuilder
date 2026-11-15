"""Export d'un set vers une playlist Rekordbox ordonnee.

Reutilise le write-path prouve de reorg_2026_09.py : backup auto de master.db
(+ masterPlaylists6.xml) AVANT toute ecriture, puis create_playlist +
add_to_playlist dans l'ordre + commit. Jamais de suppression. Reversible.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime


def backup_db(db_directory: str, dest_root: str) -> str:
    """Copie master.db (+ masterPlaylists6.xml si present) dans
    <dest_root>/<YYYYmmdd-HHMMSS>/. Retourne le dossier de backup.

    Leve FileNotFoundError si master.db est absent (on n'ecrit jamais sans
    backup reussi). La copie elle-meme peut lever (disque/permission) : on
    laisse remonter pour bloquer l'ecriture en aval.
    """
    master = os.path.join(db_directory, "master.db")
    if not os.path.isfile(master):
        raise FileNotFoundError(f"master.db introuvable dans {db_directory}")

    dest = os.path.join(dest_root, datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    shutil.copy2(master, os.path.join(dest, "master.db"))

    playlists_xml = os.path.join(db_directory, "masterPlaylists6.xml")
    if os.path.isfile(playlists_xml):
        shutil.copy2(playlists_xml, os.path.join(dest, "masterPlaylists6.xml"))

    return dest


def export_set(db, name: str, content_ids: list[str]) -> dict:
    """Cree la playlist `name` et y ajoute les `content_ids` DANS L'ORDRE,
    puis commit. `db` est duck-type (create_playlist/add_to_playlist/commit).

    content_ids vide -> ValueError (pas de playlist vide).
    Retourne {"playlist": name, "n_tracks": len(content_ids)}.
    """
    if not content_ids:
        raise ValueError("content_ids vide : rien a exporter")

    pl = db.create_playlist(name)
    for cid in content_ids:
        db.add_to_playlist(pl, cid)
    db.commit()

    return {"playlist": name, "n_tracks": len(content_ids)}
