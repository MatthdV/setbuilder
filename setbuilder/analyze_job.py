"""Statut partagé du job d'analyse (fichier JSON à côté du cache).

Le sous-process d'analyse écrit son avancement ici ; l'API le lit. Écriture
atomique (mkstemp -> os.replace) pour qu'un lecteur ne voie jamais un JSON
partiel. Lecture tolérante : jamais d'exception, un fichier absent ou corrompu
vaut `idle`, un `running` dont le pid n'est plus vivant vaut `stale`.
"""
from __future__ import annotations

import json
import os
import tempfile

STATUS_FILENAME = "analyze-status.json"


def status_path_for(cache_path: str) -> str:
    """Chemin du statut, à côté du cache."""
    return os.path.join(os.path.dirname(os.path.abspath(cache_path)), STATUS_FILENAME)


def pid_alive(pid) -> bool:
    """True si le process existe. pid None/invalide/≤0 -> False (jamais d'exception)."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def write_status(path: str, data: dict) -> None:
    """Écrit `data` en JSON de façon atomique. Aucun .tmp résiduel sur échec."""
    payload = json.dumps(data).encode("utf-8")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), suffix=".tmp")
    try:
        os.write(fd, payload)
        os.close(fd)
        fd = -1
        os.replace(tmp, path)
    except Exception:
        if fd != -1:
            os.close(fd)
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def read_status_raw(path: str) -> dict:
    """Statut stocké tel quel, sans dérivation stale. Absent/corrompu -> idle.

    Utilisé pour le compare-and-set post-spawn : la claim écrit running+pid:None,
    que read_status dériverait en `stale` ; le CAS doit comparer au brut.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return {"state": "idle"}
    return data if isinstance(data, dict) else {"state": "idle"}


def read_status(path: str) -> dict:
    """Statut courant. Absent/corrompu -> idle ; running+pid non vivant -> stale."""
    data = read_status_raw(path)
    if data.get("state") == "running" and not pid_alive(data.get("pid")):
        stale = dict(data)
        stale["state"] = "stale"
        return stale
    return data
