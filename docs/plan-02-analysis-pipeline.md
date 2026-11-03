# Set Builder — Plan 2 : Pipeline d'analyse

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyser chaque morceau de la librairie (genre, mood, énergie via Essentia ; embedding de vibe via MuQ) et en dériver une carte UMAP, le tout mis en cache dans `setbuilder.db`, en batch incrémental.

**Architecture:** Étend le package `setbuilder` du plan 1. Pour chaque track résolu : charge l'audio 16 kHz mono, calcule les features Essentia (EffNet → genre + mood + valence/arousal → energy_score) et l'embedding MuQ (1024-d mean-pooled), stocke dans une table `features`. Après le batch, UMAP sur tous les embeddings MuQ → coords `galaxy`. Idempotent/incrémental : ne réanalyse que ce qui manque.

**Tech Stack:** Python 3.12 ; `essentia-tensorflow==2.1b6.dev1389` ; `muq==0.1.0` + `torch` ; `transformers==4.44.2` + `tokenizers==0.19.1` (pin OBLIGATOIRE, cf. spike) ; `umap-learn` ; `soundfile`/`numpy` ; sqlite3 ; pytest.

**Spec:** `projets/dj-hotcues/setbuilder-design.md` (implémente §4.2 pipeline d'analyse + la base de §4.4 Galaxy ; §9 = résultats du spike de faisabilité).

## Global Constraints
- Dépend du plan 1 : table `tracks` (content_id PK), `resolve_file`, cache `setbuilder.db`. Ne jamais toucher master.db.
- **Pin dur** : `transformers==4.44.2`, `tokenizers==0.19.1` (MuQ casse avec transformers 5.x). Déclarer sous un extra `analysis` dans pyproject (hors deps par défaut, pour garder la suite de tests légère).
- Audio chargé en **16 kHz mono** (sample rate d'analyse, cohérent EffNet + spike).
- EffNet : modèle `discogs-effnet-bs64-1.pb` (essentia.upf.edu), embedding **(frames, 1280)**.
- MuQ : `OpenMuQ/MuQ-large-msd-iter`, hidden **1024-d/frame** → **mean-pool** sur les frames → vecteur (1024,) par track.
- **Incrémental** : un track déjà analysé (même content_id + `analysis_version`) est sauté. Fichier non résolu → non analysé, jamais bloquant.
- Pas de réseau hors téléchargement des poids/modèles (EffNet .pb, poids MuQ HF) au premier run.
- Les unit tests ne chargent NI modèle NI audio réel : ils testent la logique pure (formules, mean-pool, upsert, skip incrémental, wrapper UMAP) sur entrées synthétiques. L'inférence réelle est couverte par une task de smoke dédiée.

## Review Focus
- **Fichier disparu en cours de batch** : le track est marqué non-analysé/skipped, le batch continue — testé Task 7.
- **Re-run du batch** : les tracks déjà analysés (bon `analysis_version`) sont sautés, zéro recalcul — testé Task 7.
- **UMAP avec peu de points** (N < n_neighbors) : ne doit pas crasher ; fallback ou n_neighbors clampé — testé Task 6.
- **Poids/modèle indisponibles** (offline au 1er run) : erreur claire et actionnable, pas un stacktrace nu — testé Task 4/Task 7 (message), vérifié en smoke.
- **Embedding vide / audio trop court** (mean-pool sur 0 frame) : renvoie None/skip, pas de NaN silencieux — testé Task 5.

---

### Task 1 : Schéma cache des features

**Files:** Create `setbuilder/features_cache.py` ; Test `tests/test_features_cache.py`

**Interfaces:**
- Produces: `open_features(cache) -> None` (crée si absent), tables :
  `features(content_id TEXT PRIMARY KEY, top_genre TEXT, genres_json TEXT, mood_happy REAL, mood_sad REAL, mood_party REAL, mood_relaxed REAL, mood_aggressive REAL, valence REAL, arousal REAL, energy_score INTEGER, muq_embedding BLOB, muq_dim INTEGER, analysis_version TEXT, analyzed_at TEXT)`
  et `galaxy(content_id TEXT PRIMARY KEY, umap_x REAL, umap_y REAL, umap_version TEXT)`.
  `upsert_features(cache, content_id, feats: dict) -> None` (ON CONFLICT DO UPDATE) ;
  `has_features(cache, content_id, analysis_version) -> bool`.

- [ ] **Step 1: Write failing test** — `test_open_features_creates_schema` (PRAGMA table_info des 2 tables), `test_upsert_and_has_features` (upsert → has_features True ; version différente → False ; ré-upsert ne duplique pas).
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `open_features`, `upsert_features`, `has_features` dans `features_cache.py` (embedding stocké en BLOB via `np.ndarray.tobytes()`/`frombuffer`).
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** `feat(setbuilder): features + galaxy cache schema`.

---

### Task 2 : Formule energy_score

**Files:** Create `setbuilder/energy.py` ; Test `tests/test_energy.py`

**Interfaces:**
- Produces: `energy_score(arousal: float, loudness_norm: float) -> int` → entier **1–10** (formule v1 versionnée, ex. combinaison pondérée clampée). Entrées hors [0,1] clampées ; renvoie toujours 1–10.

- [ ] **Step 1: Write failing test** — `test_energy_score`: bornes (arousal=0,loud=0 → 1 ; =1,=1 → 10), monotonie (arousal plus haut → score ≥), clamp des entrées hors plage.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `energy_score` (formule simple documentée, `round`, `max(1,min(10,...))`).
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** `feat(setbuilder): energy_score formula v1`.

---

### Task 3 : Chargement audio pour analyse

**Files:** Create `setbuilder/audio.py` ; Test `tests/test_audio.py`

**Interfaces:**
- Consumes: `resolve_file` (plan 1, `setbuilder.files`).
- Produces: `load_audio_16k_mono(file_path: str) -> np.ndarray | None` (résout le chemin ; charge en 16 kHz mono float32 ; renvoie None si non résolu). Au choix via `soundfile`+resample ou `essentia.standard.MonoLoader` — l'implémenteur tranche, mais le test ne doit pas dépendre d'essentia.

- [ ] **Step 1: Write failing test** — `test_load_synthetic_wav`: écrit un wav synthétique (comme le spike : numpy+soundfile) à un sample rate ≠ 16k, charge → shape mono, longueur ≈ attendue à 16k, dtype float32. `test_load_missing_returns_none`: chemin bidon → None.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `load_audio_16k_mono` (resolve_file d'abord ; charge + convertit mono + resample 16k). Garder l'import lourd (essentia) paresseux si utilisé, pour que le test reste léger.
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** `feat(setbuilder): 16kHz mono audio loader`.

---

### Task 4 : Analyse Essentia (post-traitement testable + inférence paresseuse)

**Files:** Create `setbuilder/essentia_analyze.py` ; Test `tests/test_essentia_analyze.py`

**Interfaces:**
- Consumes: `energy_score` (Task 2).
- Produces: dataclass `EssentiaFeatures(top_genre, genres, mood_happy, mood_sad, mood_party, mood_relaxed, mood_aggressive, valence, arousal, energy_score)` ;
  `build_features(raw: dict) -> EssentiaFeatures` (pur : transforme les sorties brutes des modèles — probas genre, scores mood, valence/arousal, loudness — en dataclass, applique `energy_score`, trie/plafonne les genres) ;
  `analyze_essentia(audio: np.ndarray) -> EssentiaFeatures` (charge les modèles EffNet paresseusement, lance l'inférence, appelle `build_features`). L'inférence réelle n'est PAS unit-testée (cf. Task 8 smoke).

- [ ] **Step 1: Write failing test** — `test_build_features`: donne un `raw` synthétique (probas genre connues, moods, valence/arousal, loudness) → assert top_genre correct, genres triés par proba, energy_score cohérent, moods mappés. Entrées manquantes tolérées (None).
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `build_features` (pur) + `analyze_essentia` (inférence EffNet + têtes genre/mood/valence-arousal, imports essentia paresseux, message clair si modèle introuvable).
- [ ] **Step 4: Run, verify PASS** (unit = `build_features` seulement).
- [ ] **Step 5: Commit** `feat(setbuilder): essentia feature extraction`.

---

### Task 5 : Embedding MuQ (mean-pool testable + inférence paresseuse)

**Files:** Create `setbuilder/muq_analyze.py` ; Test `tests/test_muq_analyze.py`

**Interfaces:**
- Produces: `mean_pool(hidden: np.ndarray) -> np.ndarray | None` (pur : (frames, 1024) → (1024,) ; 0 frame → None) ;
  `analyze_muq(audio: np.ndarray) -> np.ndarray | None` (charge MuQ paresseusement `OpenMuQ/MuQ-large-msd-iter`, forward, `last_hidden_state` → `mean_pool`). Inférence réelle non unit-testée (Task 8).

- [ ] **Step 1: Write failing test** — `test_mean_pool`: (frames,1024) synthétique → (1024,), valeurs = moyenne par dim ; (0,1024) → None ; 1D invalide géré.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `mean_pool` (numpy, axis=0) + `analyze_muq` (import torch/muq paresseux ; `with torch.no_grad()` ; `output_hidden_states=True` ; vers numpy).
- [ ] **Step 4: Run, verify PASS** (unit = `mean_pool`).
- [ ] **Step 5: Commit** `feat(setbuilder): MuQ embedding (mean-pooled)`.

---

### Task 6 : Carte UMAP (Galaxy)

**Files:** Create `setbuilder/galaxy.py` ; Test `tests/test_galaxy.py`

**Interfaces:**
- Produces: `fit_umap(embeddings: np.ndarray, seed: int = 42) -> np.ndarray` ((N,1024) → (N,2)). **n_neighbors clampé à min(15, N-1)** ; N < 3 → renvoie des coords triviales (ex. zéros/placés) sans crasher.

- [ ] **Step 1: Write failing test** — `test_fit_umap_shape`: (50,1024) aléatoire seedé → (50,2) fini (pas de NaN), déterministe à seed fixe. `test_fit_umap_few_points`: N=2 → (2,2) sans exception.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `fit_umap` (umap-learn, `random_state=seed`, n_neighbors clampé, garde-fou petit N). Import umap paresseux.
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** `feat(setbuilder): UMAP galaxy projection`.

---

### Task 7 : Batch `analyze` + CLI (orchestration incrémentale)

**Files:** Create `setbuilder/analyze.py` ; Modify `setbuilder/__main__.py` (ajoute la sous-commande `analyze`) ; Test `tests/test_analyze.py`

**Interfaces:**
- Consumes: `open_features/upsert_features/has_features` (T1), `load_audio_16k_mono` (T3), `analyze_essentia` (T4), `analyze_muq` (T5), `fit_umap` (T6), `tracks` du cache (plan 1).
- Produces: `run_analyze(cache, *, analyzers, analysis_version) -> AnalyzeStats(analyzed, skipped, missing, failed)` — itère les tracks avec fichier résolvable et sans features à jour ; pour chacun charge l'audio, appelle les analyzers injectés (essentia+muq), upsert ; collecte les embeddings ; à la fin `fit_umap` et remplit `galaxy`. `analyzers` est injectable pour tester sans modèles. CLI `python -m setbuilder analyze` câble les vrais analyzers.

- [ ] **Step 1: Write failing test** — `test_run_analyze_incremental` (analyzers factices déterministes, cache temp avec 3 tracks dont 1 à fichier manquant) : 1er run → analyzed=2, missing=1 ; 2e run → skipped=2, analyzed=0 ; galaxy peuplée pour les analysés. `test_run_analyze_continues_on_missing` : le fichier manquant n'interrompt pas. `test_run_analyze_counts_failure` : un analyzer qui lève sur un track → failed +1, les autres continuent.
- [ ] **Step 2: Run, verify FAIL.**
- [ ] **Step 3: Implement** `run_analyze` (skip via `has_features` ; try/except par track → failed ; collecte embeddings → `fit_umap` → upsert galaxy) + sous-commande CLI `analyze` (vrais analyzers, barre de progression simple, refuse si Rekordbox tourne comme `sync`).
- [ ] **Step 4: Run, verify PASS.**
- [ ] **Step 5: Commit** `feat(setbuilder): incremental analyze batch + CLI`.

---

### Task 8 : Smoke réel du stack + extra `analysis`

**Files:** Modify `pyproject.toml` (extra `analysis`) ; Modify `README.md` ; Create `scripts/smoke_analysis.py` (hors package, non importé par les tests)

**Interfaces:** aucune nouvelle interface de prod. Vérifie que le vrai stack tourne bout en bout sur quelques tracks.

- [ ] **Step 1:** Ajouter `[project.optional-dependencies] analysis = ["essentia-tensorflow==2.1b6.dev1389", "torch", "muq==0.1.0", "transformers==4.44.2", "tokenizers==0.19.1", "umap-learn", "soundfile", "numpy"]` ; README : installer avec `uv sync --extra analysis` ; noter le pin transformers et le run de nuit pour MuQ.
- [ ] **Step 2:** `scripts/smoke_analysis.py` : prend 2–3 fichiers audio (chemins en argument, ou génère un wav synthétique comme le spike) → `load_audio_16k_mono` → `analyze_essentia` + `analyze_muq` → `fit_umap` sur les embeddings → imprime features + shapes + temps. Pas un test pytest (modèles lourds).
- [ ] **Step 3:** Lancer le smoke (contrôleur/implémenteur) sur un petit lot ; confirmer : EffNet (frames,1280), MuQ (1024,), UMAP (N,2), temps cohérents avec le spike (EffNet ~1–2 s, MuQ ~15–20 s / 3 min). Consigner le résultat dans le rapport.
- [ ] **Step 4:** `uv run pytest` reste vert et SANS dépendance analysis (les modèles ne sont pas importés par la suite).
- [ ] **Step 5: Commit** `chore(setbuilder): analysis extra + real-stack smoke`.

---

## Self-review
- **Spec coverage** : §4.2 embedding MuQ → T5 ; genre/mood/energy Essentia → T4+T2 ; UMAP → T6 ; cache features → T1 ; audio 16k → T3 ; batch incrémental + missing → T7 ; pins & faisabilité (§9) → T8 + Global Constraints. Set builder/scoring/API/front/export = plans suivants.
- **Review Focus** : fichier disparu→T7 ; re-run incrémental→T7 ; UMAP petit N→T6 ; modèle offline→T4/T7+smoke ; embedding vide→T5. Couverts.
- **Type consistency** : `content_id`, `EssentiaFeatures`, `analyze_essentia`, `analyze_muq`, `mean_pool`, `fit_umap`, `run_analyze`, `upsert_features/has_features` cohérents entre tasks ; `analysis_version` passé partout où le skip en dépend.
- **Proportion** : signatures + noms de tests + assertions, corps laissés à l'implémenteur. Pas de transcript.
- **Découpage** : unit tests sans modèles/audio (logique pure) ; inférence réelle isolée en T8 smoke — même stratégie que plan 1 (fake rows + smoke réel).

## Vérification (fin de plan)
- `uv run pytest` vert, suite sans dépendance `analysis`.
- Smoke T8 : EffNet + MuQ + UMAP tournent bout en bout sur quelques tracks, shapes et temps cohérents avec le §9.
- `python -m setbuilder analyze` sur un petit lot réel → features + galaxy peuplées dans `setbuilder.db` ; 2e run → tout skippé ; fichier manquant non bloquant ; master.db intact.
