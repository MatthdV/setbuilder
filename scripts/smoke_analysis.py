"""Smoke du vrai stack (EffNet + MuQ + UMAP). Non importé par pytest.

Usage : uv run --extra analysis python scripts/smoke_analysis.py [fichier.mp3 ...]
Sans argument : génère 3 wav synthétiques (~20 s) dans un dossier temporaire.
"""

import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from setbuilder.audio import load_audio_16k_mono
from setbuilder.essentia_analyze import analyze_essentia
from setbuilder.galaxy import fit_umap
from setbuilder.muq_analyze import analyze_muq


def synthetic_files(n=3, secs=20, sr=44100) -> list[str]:
    tmp = Path(tempfile.mkdtemp(prefix="sb_smoke_"))
    rng = np.random.default_rng(0)
    out = []
    for i in range(n):
        t = np.arange(sr * secs) / sr
        kick = np.sin(2 * np.pi * (50 + 10 * i) * t) * (np.sin(2 * np.pi * (2 + i) * t) > 0)
        sig = 0.4 * kick + 0.1 * np.sin(2 * np.pi * (220 * (i + 1)) * t) + 0.02 * rng.normal(size=t.size)
        path = tmp / f"synth{i}.wav"
        sf.write(path, sig.astype(np.float32), sr)
        out.append(str(path))
    return out


def main() -> None:
    files = sys.argv[1:] or synthetic_files()
    embs = []
    for f in files:
        audio = load_audio_16k_mono(f)
        assert audio is not None, f"introuvable : {f}"
        t0 = time.time(); feats = analyze_essentia(audio); t_e = time.time() - t0
        t0 = time.time(); emb = analyze_muq(audio); t_m = time.time() - t0
        print(f"{Path(f).name}: {len(audio)/16000:.0f}s audio | essentia {t_e:.1f}s | muq {t_m:.1f}s")
        print(f"  {feats}")
        print(f"  muq shape={None if emb is None else emb.shape}")
        if emb is not None:
            embs.append(emb)
    coords = fit_umap(np.stack(embs))
    print(f"umap shape={coords.shape}")


if __name__ == "__main__":
    main()
