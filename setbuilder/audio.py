"""Chargement audio pour l'analyse : 16 kHz mono float32."""

from math import gcd

import numpy as np

from setbuilder.files import resolve_file

TARGET_SR = 16000


def load_audio_16k_mono(file_path: str) -> np.ndarray | None:
    """Résout le chemin (fallback NFC/NFD) puis charge en 16 kHz mono float32.

    Renvoie None si le fichier est introuvable ou illisible.
    """
    resolved, _status = resolve_file(file_path)
    if resolved is None:
        return None

    import soundfile as sf  # imports paresseux : garde le module léger
    from scipy.signal import resample_poly

    try:
        data, sr = sf.read(resolved, dtype="float32", always_2d=True)
    except (RuntimeError, sf.LibsndfileError):
        return _load_with_essentia(resolved)  # m4a/aac etc. non gérés par libsndfile

    mono = data.mean(axis=1)
    if sr != TARGET_SR:
        g = gcd(int(sr), TARGET_SR)
        mono = resample_poly(mono, TARGET_SR // g, int(sr) // g)
    return np.ascontiguousarray(mono, dtype=np.float32)


def _load_with_essentia(path: str) -> np.ndarray | None:
    """Fallback ffmpeg via essentia MonoLoader (extra `analysis`). None si indisponible."""
    try:
        from essentia.standard import MonoLoader

        return np.ascontiguousarray(
            MonoLoader(filename=path, sampleRate=TARGET_SR)(), dtype=np.float32
        )
    except Exception:  # essentia absent ou fichier illisible
        return None
