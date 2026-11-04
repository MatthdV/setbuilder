# setbuilder

Outil perso de préparation de sets DJ sur la librairie Rekordbox.
Voir le doc de conception et les plans dans le vault (projets/dj-hotcues/).

## Installation

Le CLI `python -m setbuilder sync` a besoin de pyrekordbox : `uv sync --extra rekordbox`.
La suite de tests n'a besoin d'aucun extra (`uv run pytest`).

## Analyse audio (Plan 2)

`python -m setbuilder analyze` calcule, par morceau, genre / mood / énergie (Essentia) et un
embedding de vibe (MuQ), puis la carte UMAP. Tout est écrit dans `setbuilder.db`, jamais dans master.db.
Incrémental : un track déjà analysé (même `analysis_version`) est sauté ; fichier introuvable = ignoré.

```bash
uv sync --extra analysis
uv run python scripts/smoke_analysis.py            # smoke sur audio synthétique
uv run python -m setbuilder analyze
```

- **Pin obligatoire** : `transformers==4.44.2` + `tokenizers==0.19.1` (MuQ plante avec transformers 5.x).
- Premier run : téléchargement des modèles Essentia (`~/.cache/setbuilder/models`, variable
  `SETBUILDER_MODELS`) et des poids MuQ (Hugging Face). Hors-ligne, la commande s'arrête avec un message clair.
- MuQ est le goulot (~15-20 s par morceau de 3 min sur CPU, ~20 h pour 4136 titres) : à lancer de nuit.
  `SETBUILDER_DEVICE=mps` tente l'accélération Apple Silicon (non défaut).
- `uv run pytest` n'a pas besoin de l'extra `analysis` (aucun modèle chargé).
