"""Résolution de fichiers audio sur clé FAT32.

Rekordbox enregistre les chemins dans une normalisation Unicode donnée (NFC ou NFD),
alors que la clé peut les stocker dans l'autre forme. On teste donc le chemin tel quel,
puis le basename en NFC et en NFD, dans le même dossier.
"""

import os
import unicodedata


def resolve_file(file_path: str) -> tuple[str | None, str]:
    """Renvoie (chemin_résolu, "ok") ou (None, "missing")."""
    if os.path.exists(file_path):
        return file_path, "ok"

    dirname, basename = os.path.split(file_path)
    for form in ("NFC", "NFD"):
        candidate = os.path.join(dirname, unicodedata.normalize(form, basename))
        if os.path.exists(candidate):
            return candidate, "ok"

    return None, "missing"
