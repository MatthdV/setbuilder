"""Lance l'analyse dans un sous-process détaché.

L'app web ne charge jamais torch/MuQ : elle spawn `python -m setbuilder analyze`
dans un process séparé qui survit à la fermeture de l'onglet (start_new_session).
"""
import subprocess
import sys


def spawn_analyze(cache_path: str, status_path: str) -> int:
    """Spawn l'analyse détachée et renvoie le pid du sous-process."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "setbuilder", "analyze",
         "--cache", cache_path, "--status-file", status_path],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid
