"""Genre / mood / énergie via Essentia (discogs-effnet + têtes MTG).

`build_features` et `loudness_norm` sont purs et testés unitairement ;
`analyze_essentia` charge les modèles paresseusement (extra `analysis`).
"""

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from setbuilder.energy import energy_score
from setbuilder.errors import AnalysisUnavailableError

MAX_GENRES = 5
BASE_URL = "https://essentia.upf.edu/models/"
SR = 16000

# nom de fichier -> chemin relatif sur essentia.upf.edu/models/
_MODEL_PATHS = {
    "discogs-effnet-bs64-1.pb": "feature-extractors/discogs-effnet/",
    "genre_discogs400-discogs-effnet-1.pb": "classification-heads/genre_discogs400/",
    "genre_discogs400-discogs-effnet-1.json": "classification-heads/genre_discogs400/",
    "msd-musicnn-1.pb": "feature-extractors/musicnn/",
    "deam-msd-musicnn-2.pb": "classification-heads/deam/",
}
_MOODS = ("happy", "sad", "party", "relaxed", "aggressive")
for _m in _MOODS:
    for _ext in ("pb", "json"):
        _MODEL_PATHS[f"mood_{_m}-discogs-effnet-1.{_ext}"] = f"classification-heads/mood_{_m}/"


class ModelUnavailableError(AnalysisUnavailableError):
    """Modèle Essentia introuvable et non téléchargeable (hors-ligne au premier run)."""


@dataclass
class EssentiaFeatures:
    top_genre: str | None
    genres: list[tuple[str, float]]
    mood_happy: float | None
    mood_sad: float | None
    mood_party: float | None
    mood_relaxed: float | None
    mood_aggressive: float | None
    valence: float | None
    arousal: float | None
    energy_score: int | None


def build_features(raw: dict) -> EssentiaFeatures:
    """Transforme les sorties brutes des modèles (valeurs dans [0,1]) en EssentiaFeatures.

    `raw` : genre_probs {label: proba}, mood_*, valence, arousal, loudness_norm — tout optionnel.
    """
    probs = raw.get("genre_probs") or {}
    genres = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:MAX_GENRES]
    genres = [(g, float(p)) for g, p in genres]

    arousal = raw.get("arousal")
    loud = raw.get("loudness_norm")
    energy = None
    if arousal is not None or loud is not None:
        energy = energy_score(0.5 if arousal is None else arousal, 0.5 if loud is None else loud)

    return EssentiaFeatures(
        top_genre=genres[0][0] if genres else None,
        genres=genres,
        mood_happy=raw.get("mood_happy"),
        mood_sad=raw.get("mood_sad"),
        mood_party=raw.get("mood_party"),
        mood_relaxed=raw.get("mood_relaxed"),
        mood_aggressive=raw.get("mood_aggressive"),
        valence=raw.get("valence"),
        arousal=arousal,
        energy_score=energy,
    )


def to_cache_dict(f: EssentiaFeatures) -> dict:
    """Colonnes de la table `features` correspondant à ces features."""
    return {
        "top_genre": f.top_genre,
        "genres_json": json.dumps(f.genres),
        "mood_happy": f.mood_happy,
        "mood_sad": f.mood_sad,
        "mood_party": f.mood_party,
        "mood_relaxed": f.mood_relaxed,
        "mood_aggressive": f.mood_aggressive,
        "valence": f.valence,
        "arousal": f.arousal,
        "energy_score": f.energy_score,
    }


def loudness_norm(audio: np.ndarray) -> float:
    """RMS en dBFS mappé linéairement : -30 dB -> 0, -6 dB -> 1 (clampé)."""
    if audio.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    if rms <= 1e-9:
        return 0.0
    db = 20.0 * np.log10(rms)
    return float(max(0.0, min(1.0, (db + 30.0) / 24.0)))


def models_dir() -> Path:
    return Path(os.environ.get("SETBUILDER_MODELS", Path.home() / ".cache" / "setbuilder" / "models"))


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as out:
        while chunk := r.read(1 << 20):
            out.write(chunk)
    tmp.replace(dest)


def ensure_model(name: str) -> Path:
    """Chemin local du modèle, téléchargé au premier usage. Erreur claire si indisponible."""
    dest = models_dir() / name
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = BASE_URL + _MODEL_PATHS[name] + name
    try:
        _download(url, dest)
    except OSError as e:
        raise ModelUnavailableError(
            f"Modèle Essentia '{name}' introuvable et téléchargement impossible ({e}). "
            f"Premier run hors-ligne ? Connecte-toi, ou place le fichier dans "
            f"{dest.parent} (variable SETBUILDER_MODELS pour changer le dossier). URL : {url}"
        ) from e
    return dest


_models: dict | None = None


def _load_models() -> dict:
    """Charge (une fois) EffNet, musicnn et toutes les têtes. Imports essentia paresseux."""
    global _models
    if _models is not None:
        return _models
    try:
        from essentia.standard import (
            TensorflowPredict2D,
            TensorflowPredictEffnetDiscogs,
            TensorflowPredictMusiCNN,
        )
    except ImportError as e:
        raise ModelUnavailableError(
            "essentia-tensorflow absent : installe l'extra avec `uv sync --extra analysis`."
        ) from e

    m: dict = {}
    m["effnet"] = TensorflowPredictEffnetDiscogs(
        graphFilename=str(ensure_model("discogs-effnet-bs64-1.pb")), output="PartitionedCall:1")
    genre_pb = ensure_model("genre_discogs400-discogs-effnet-1.pb")
    genre_json = ensure_model("genre_discogs400-discogs-effnet-1.json")
    m["genre_labels"] = json.loads(genre_json.read_text())["classes"]
    m["genre"] = TensorflowPredict2D(
        graphFilename=str(genre_pb), input="serving_default_model_Placeholder",
        output="PartitionedCall:0")
    for mood in _MOODS:
        pb = ensure_model(f"mood_{mood}-discogs-effnet-1.pb")
        classes = json.loads(ensure_model(f"mood_{mood}-discogs-effnet-1.json").read_text())["classes"]
        m[f"mood_{mood}"] = (
            TensorflowPredict2D(graphFilename=str(pb), output="model/Softmax"),
            classes.index(mood),
        )
    m["musicnn"] = TensorflowPredictMusiCNN(
        graphFilename=str(ensure_model("msd-musicnn-1.pb")), output="model/dense/BiasAdd")
    m["deam"] = TensorflowPredict2D(
        graphFilename=str(ensure_model("deam-msd-musicnn-2.pb")), output="model/Identity")
    _models = m
    return m


def analyze_essentia(audio: np.ndarray) -> EssentiaFeatures:
    """Inférence réelle sur un signal 16 kHz mono float32."""
    m = _load_models()
    emb = m["effnet"](audio)  # (frames, 1280)
    genre = np.asarray(m["genre"](emb)).mean(axis=0)
    raw: dict = {"genre_probs": {m["genre_labels"][i]: float(genre[i]) for i in range(len(genre))}}
    for mood in _MOODS:
        model, idx = m[f"mood_{mood}"]
        raw[f"mood_{mood}"] = float(np.asarray(model(emb)).mean(axis=0)[idx])
    # valence/arousal : DEAM sur embeddings musicnn, échelle 1-9 -> [0,1]
    va = np.asarray(m["deam"](m["musicnn"](audio))).mean(axis=0)
    raw["valence"] = float(np.clip((va[0] - 1.0) / 8.0, 0.0, 1.0))
    raw["arousal"] = float(np.clip((va[1] - 1.0) / 8.0, 0.0, 1.0))
    raw["loudness_norm"] = loudness_norm(audio)
    return build_features(raw)
