# Set Builder — Plan 3 : Moteur de scoring des suggestions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommandé) ou superpowers:executing-plans pour exécuter ce plan tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`).

**Goal:** Donner, pour un slot de set (morceau précédent + cible d'énergie locale), un classement explicable de toute la librairie par compatibilité (key, BPM, énergie, vibe, ambiance).

**Architecture:** Moteur 100 % pur en Python sur les features déjà en cache (plans 1 & 2). Chaque dimension est une fonction isolée qui rend `(label_explicable, sous-score 0-1)` ; `scoring.py` combine les dimensions avec des poids versionnés et ajustables en un `ScoreBreakdown` (score 0-100 + détail par dimension). Un seul accès I/O : `candidates.py` charge les candidats depuis `setbuilder.db` (jointure `tracks` + `features`). Zéro réseau, zéro modèle ML, zéro master.db.

**Tech Stack:** Python 3.12, numpy (cosine), sqlite3 (lecture du cache local). Pas de nouvelle dépendance lourde. Tests `uv run pytest` (pythonpath déjà configuré).

**Spec:** `projets/dj-hotcues/setbuilder-design.md` (§4.3 scoring, §4.4 modèle de set). Copie repo : `docs/design.md`.

## Global Constraints

- **Moteur pur** : seul `candidates.py` lit `setbuilder.db` ; toutes les autres fonctions prennent leurs entrées en argument et ne font aucun I/O. Jamais de lecture/écriture de master.db.
- **Explicable, jamais opaque** : chaque dimension rend un `label` lisible (ex. `"key ✓"`, `"+2.3% BPM"`, `"énergie ↗"`) ; `ScoreBreakdown` expose le détail par dimension. Aucun score sans détail.
- **Poids ajustables et versionnés** : les poids vivent dans une dataclass `Weights` avec une constante `SCORING_VERSION` ; changer un poids ou une formule incrémente la version.
- **Candidats = toute la lib par défaut** : filtres genre / My Tag optionnels pour réduire le bruit, jamais obligatoires.
- **Dégradation douce** : une donnée manquante (pas de camelot, pas de BPM, morceau non analysé, embedding absent/non fini) rend un sous-score **neutre** avec un label explicite, jamais une exception ni un 0 qui masque le morceau.
- **Embeddings** : lus depuis `features.muq_embedding` (float32 BLOB) + `features.muq_dim` ; `energy_score` est un entier 1-10 déjà en cache (`features.energy_score`).
- Convention de code et style des modules existants (`camelot.py`, `energy.py`) : docstrings FR, fonctions courtes et pures.

## Review Focus

- **Candidat sans camelot ou BPM** : sous-score neutre + label `"key inconnue"` / `"BPM inconnu"`, jamais d'exception ni d'exclusion silencieuse → couvert Tâches 1, 2.
- **Morceau non analysé / embedding absent ou non fini** : `candidates.py` le charge quand même (dimensions ML neutres) ; `vibe_score` rend neutre sur `None`/NaN → couvert Tâches 4, 7.
- **Slot sans morceau précédent** (1er slot du set) : key/BPM/vibe sans contexte rendent neutre, l'énergie et l'ambiance scorent seules → couvert Tâche 6.
- **Position de courbe hors [0,1]** : `target_at` clampe au lieu d'extrapoler → couvert Tâche 3.
- **Liste de candidats vide** (filtre trop serré) : `rank` rend `[]` sans erreur → couvert Tâche 7.

---

### Task 1 : Compatibilité harmonique (Camelot)

**Files:**
- Create: `setbuilder/harmony.py`
- Test: `tests/test_harmony.py`

**Interfaces:**
- Consumes: la notation Camelot produite par `setbuilder.camelot.to_camelot` (`"8A"`, `"12B"`, ou `None`).
- Produces: `camelot_compat(a: str | None, b: str | None) -> tuple[str, float]` — `(label, sous-score 0..1)`.

- [ ] **Step 1: Write the failing test**

```python
from setbuilder.harmony import camelot_compat

def test_same_key_is_perfect():
    assert camelot_compat("8A", "8A") == ("key ✓ (même)", 1.0)

def test_adjacent_wheel():
    # ±1 sur la roue, même lettre ; 12 et 1 sont adjacents (modulo 12)
    assert camelot_compat("8A", "9A")[1] == 0.9
    assert camelot_compat("12B", "1B")[1] == 0.9

def test_relative_major_minor():
    # même numéro, lettre opposée
    assert camelot_compat("8A", "8B")[1] == 0.85

def test_energy_boost_plus_two():
    assert camelot_compat("8A", "10A")[1] == 0.6

def test_incompatible():
    assert camelot_compat("8A", "3B")[1] == 0.0

def test_unknown_key_is_neutral():
    assert camelot_compat("8A", None) == ("key inconnue", 0.5)
    assert camelot_compat(None, "8A") == ("key inconnue", 0.5)
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_harmony.py -v` → FAIL (module absent).
- [ ] **Step 3: Implement `camelot_compat(a, b)` in `setbuilder/harmony.py`**

Parse `"<n><A|B>"` en `(numéro 1-12, lettre)`. Distance sur la roue = `min((n1-n2) % 12, (n2-n1) % 12)`. Règles : même clé → `1.0` ; distance 1 même lettre → `0.9` ; même numéro lettre opposée (relatif) → `0.85` ; distance 2 même lettre (energy boost) → `0.6` ; sinon → `0.0`. Entrée non Camelot ou `None` → `("key inconnue", 0.5)`. Label parlant par cas.

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_harmony.py -v` → PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): harmonic Camelot compatibility`.

---

### Task 2 : Compatibilité BPM

**Files:**
- Create: `setbuilder/bpm.py`
- Test: `tests/test_bpm.py`

**Interfaces:**
- Produces: `bpm_compat(prev: float | None, cand: float | None, tolerance: float = 0.06) -> tuple[str, float]`.

- [ ] **Step 1: Write the failing test**

```python
from setbuilder.bpm import bpm_compat

def test_identical_bpm_perfect():
    label, s = bpm_compat(128.0, 128.0)
    assert s == 1.0 and "0" in label

def test_within_tolerance_high():
    assert bpm_compat(128.0, 131.0)[1] > 0.8   # +2.3 %, dans ±6 %

def test_beyond_tolerance_penalised():
    assert bpm_compat(128.0, 150.0)[1] < 0.3    # +17 %

def test_half_double_time_recognised():
    # 64 ↔ 128 est mixable (double-time), score élevé + label qui le dit
    label, s = bpm_compat(128.0, 64.0)
    assert s > 0.8 and "½" in label or "x2" in label

def test_unknown_bpm_neutral():
    assert bpm_compat(None, 128.0) == ("BPM inconnu", 0.5)
    assert bpm_compat(128.0, None) == ("BPM inconnu", 0.5)
```

- [ ] **Step 2: Run to verify it fails** — FAIL (module absent).
- [ ] **Step 3: Implement `bpm_compat(prev, cand, tolerance)` in `setbuilder/bpm.py`**

Compare `cand` à `prev`, `2*prev`, `prev/2` ; retiens le ratio dont l'écart relatif `|r-1|` est le plus petit (gère half/double-time). Écart `d = |r-1|`. Score : `1.0` à `d=0`, décroissance linéaire jusqu'à `0.0` à `d = 4*tolerance` (soit ±24 %), clampé `[0,1]`. Label : pourcentage signé (`"+2.3% BPM"`), avec suffixe `"(x2)"` / `"(½)"` si l'appariement passe par le double/moitié. `None` → `("BPM inconnu", 0.5)`.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): BPM compatibility with half/double-time`.

---

### Task 3 : Courbe d'énergie cible

**Files:**
- Create: `setbuilder/curve.py`
- Test: `tests/test_curve.py`

**Interfaces:**
- Produces: `EnergyCurve.from_points(points: list[tuple[float, float]]) -> EnergyCurve` et `EnergyCurve.target_at(pos: float) -> float` (position normalisée 0-1 → énergie cible 1-10).
- Consumed by: Tâche 5 (`energy_fit`) et le contexte de slot (Tâche 6).

- [ ] **Step 1: Write the failing test**

```python
import pytest
from setbuilder.curve import EnergyCurve

def test_linear_interpolation():
    c = EnergyCurve.from_points([(0.0, 2.0), (0.5, 8.0), (1.0, 4.0)])
    assert c.target_at(0.0) == 2.0
    assert c.target_at(0.5) == 8.0
    assert c.target_at(0.25) == 5.0        # milieu de la 1re rampe

def test_position_clamped_not_extrapolated():
    c = EnergyCurve.from_points([(0.0, 2.0), (1.0, 9.0)])
    assert c.target_at(-0.5) == 2.0
    assert c.target_at(1.5) == 9.0

def test_single_point_is_flat():
    c = EnergyCurve.from_points([(0.0, 6.0)])
    assert c.target_at(0.3) == 6.0

def test_empty_rejected():
    with pytest.raises(ValueError):
        EnergyCurve.from_points([])
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement `EnergyCurve` in `setbuilder/curve.py`**

Dataclass portant les points triés par position. `from_points` : rejette la liste vide (`ValueError`), trie, dé-duplique les positions. `target_at` : clampe `pos` à `[points[0].x, points[-1].x]` puis interpole linéairement entre les deux points encadrants (point unique → valeur constante).

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): target energy curve with clamped interpolation`.

---

### Task 4 : Proximité de vibe (cosine MuQ)

**Files:**
- Create: `setbuilder/vibe.py`
- Test: `tests/test_vibe.py`

**Interfaces:**
- Consumes: embeddings `np.ndarray` (float32, dim = `muq_dim`) ou `None`.
- Produces: `vibe_score(a: np.ndarray | None, b: np.ndarray | None) -> tuple[str, float]`.

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from setbuilder.vibe import vibe_score

def test_same_vector_max():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    label, s = vibe_score(v, v)
    assert s == 1.0

def test_orthogonal_is_mid():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert vibe_score(a, b)[1] == 0.5          # cosine 0 -> (0+1)/2

def test_opposite_is_zero():
    a = np.array([1.0, 0.0], dtype=np.float32)
    assert vibe_score(a, -a)[1] == 0.0

def test_missing_or_nonfinite_neutral():
    v = np.array([1.0, 0.0], dtype=np.float32)
    assert vibe_score(None, v) == ("vibe n/a", 0.5)
    assert vibe_score(np.array([np.nan, 0.0], dtype=np.float32), v) == ("vibe n/a", 0.5)
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement `vibe_score(a, b)` in `setbuilder/vibe.py`**

`None`, norme nulle ou valeurs non finies dans l'un des vecteurs → `("vibe n/a", 0.5)`. Sinon `cos = dot(a,b)/(‖a‖‖b‖)`, mappé `[-1,1] → [0,1]` par `(cos+1)/2`, clampé. Label : `"vibe <pct>%"` (de la similarité mappée).

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): MuQ cosine vibe proximity`.

---

### Task 5 : Écart à la courbe + bonus d'ambiance

**Files:**
- Create: `setbuilder/fit.py`
- Test: `tests/test_fit.py`

**Interfaces:**
- Produces:
  - `energy_fit(cand_energy: int | None, target: float) -> tuple[str, float]`
  - `tag_bonus(cand_moment: str | None, cand_ambiance: str | None, slot_moment: str | None, slot_ambiance: str | None) -> tuple[str, float]`

- [ ] **Step 1: Write the failing test**

```python
from setbuilder.fit import energy_fit, tag_bonus

def test_energy_on_target_perfect():
    assert energy_fit(8, 8.0)[1] == 1.0

def test_energy_gap_direction_labelled():
    assert "↗" in energy_fit(5, 8.0)[0]   # candidat sous la cible -> doit monter
    assert "↘" in energy_fit(9, 6.0)[0]

def test_energy_far_low_score():
    assert energy_fit(1, 10.0)[1] == 0.0  # écart max de 9 points

def test_energy_unknown_neutral():
    assert energy_fit(None, 7.0) == ("énergie n/a", 0.5)

def test_tag_match_bonus():
    assert tag_bonus("Peak", "Dark", "Peak", "Dark")[1] == 1.0
    assert tag_bonus("Warm-up", None, "Peak", None)[1] == 0.0
    assert tag_bonus(None, None, "Peak", "Dark") == ("ambiance n/a", 0.5)
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement in `setbuilder/fit.py`**

`energy_fit` : `None` → `("énergie n/a", 0.5)`. Sinon `gap = |cand - target|` sur 0-9, score `1 - gap/9` clampé. Label `"énergie ↗"` si `cand < target - 0.5`, `"↘"` si `cand > target + 0.5`, sinon `"="`. `tag_bonus` : si les deux côtés (moment, ambiance) sont `None` → `("ambiance n/a", 0.5)` ; sinon fraction des champs renseignés du slot qui matchent le candidat (moment et/ou ambiance), label listant ce qui colle.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): energy-vs-curve fit and ambiance bonus`.

---

### Task 6 : Agrégation pondérée explicable

**Files:**
- Create: `setbuilder/scoring.py`
- Test: `tests/test_scoring.py`

**Interfaces:**
- Consumes: `harmony.camelot_compat`, `bpm.bpm_compat`, `fit.energy_fit`, `fit.tag_bonus`, `vibe.vibe_score`.
- Produces:
  - `Candidate` (dataclass) : `content_id: str`, `title: str | None`, `artist: str | None`, `bpm: float | None`, `camelot: str | None`, `energy: int | None`, `moment: str | None`, `ambiance: str | None`, `embedding: np.ndarray | None`.
  - `SlotContext` (dataclass) : `prev: Candidate | None`, `target_energy: float`, `slot_moment: str | None = None`, `slot_ambiance: str | None = None`.
  - `Weights` (dataclass, défauts ajustables) + `SCORING_VERSION: str`.
  - `score_candidate(cand: Candidate, ctx: SlotContext, weights: Weights = DEFAULT_WEIGHTS) -> ScoreBreakdown`.
  - `ScoreBreakdown` (dataclass) : `content_id`, `score: int` (0-100), `dimensions: dict[str, tuple[str, float]]` (nom → (label, sous-score)).

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from setbuilder.scoring import Candidate, SlotContext, score_candidate, DEFAULT_WEIGHTS, SCORING_VERSION

def _cand(**kw):
    base = dict(content_id="c", title=None, artist=None, bpm=128.0, camelot="8A",
               energy=7, moment=None, ambiance=None, embedding=None)
    base.update(kw); return Candidate(**base)

def test_perfect_match_scores_high():
    prev = _cand(content_id="p")
    ctx = SlotContext(prev=prev, target_energy=7.0)
    b = score_candidate(_cand(camelot="8A", bpm=128.0, energy=7), ctx)
    assert b.score >= 90
    assert "key" in b.dimensions and "bpm" in b.dimensions and "energy" in b.dimensions

def test_breakdown_is_explainable():
    ctx = SlotContext(prev=_cand(), target_energy=7.0)
    b = score_candidate(_cand(camelot="3B"), ctx)      # clash de key
    assert b.dimensions["key"][1] == 0.0               # sous-score exposé

def test_first_slot_no_prev_neutralises_relative_dims():
    ctx = SlotContext(prev=None, target_energy=5.0)
    b = score_candidate(_cand(energy=5), ctx)
    assert b.dimensions["key"][1] == 0.5               # pas de contexte -> neutre
    assert b.dimensions["bpm"][1] == 0.5

def test_weights_versioned():
    assert isinstance(SCORING_VERSION, str) and SCORING_VERSION
    assert abs(sum([DEFAULT_WEIGHTS.key, DEFAULT_WEIGHTS.bpm, DEFAULT_WEIGHTS.energy,
                    DEFAULT_WEIGHTS.vibe, DEFAULT_WEIGHTS.ambiance]) - 1.0) < 1e-9
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement in `setbuilder/scoring.py`**

`Weights` : `key`, `bpm`, `energy`, `vibe`, `ambiance` (somme = 1.0 ; défaut pondéré key fort, ex. `0.30/0.20/0.20/0.20/0.10`). `SCORING_VERSION = "scoring-v1"`. `score_candidate` : si `ctx.prev is None`, key/bpm/vibe passent des entrées `None` (donc neutres 0.5) ; sinon compare au `prev`. Chaque dimension appelle sa fonction → `(label, sous-score)`. Score final = `round(100 * Σ poids_i * sous-score_i)`. Remplit `dimensions` avec les 5 `(label, sous-score)`.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): weighted explainable score aggregation`.

---

### Task 7 : Chargement des candidats + classement

**Files:**
- Create: `setbuilder/candidates.py`
- Test: `tests/test_candidates.py`

**Interfaces:**
- Consumes: `setbuilder.cache.open_cache` (table `tracks`), `setbuilder.features_cache` (table `features`), `scoring.Candidate`, `scoring.score_candidate`.
- Produces:
  - `load_candidates(cache, analysis_version: str, *, genres: list[str] | None = None, moments: list[str] | None = None) -> list[Candidate]` — jointure `tracks` ⨝ `features` (LEFT : un morceau non analysé reste candidat, features ML à neutre), filtres optionnels.
  - `rank(candidates: list[Candidate], ctx: SlotContext, weights=DEFAULT_WEIGHTS, *, exclude_ids: set[str] | None = None) -> list[ScoreBreakdown]` — triée score décroissant, exclut `exclude_ids` (morceaux déjà posés dans le set).

- [ ] **Step 1: Write the failing test** (monte un `setbuilder.db` en mémoire, insère 2-3 tracks + features via les helpers existants, vérifie)

```python
import sqlite3, numpy as np
from setbuilder.features_cache import open_features, upsert_features
from setbuilder.candidates import load_candidates, rank
from setbuilder.scoring import SlotContext, Candidate

def _db():
    c = sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE tracks (content_id TEXT PRIMARY KEY, title TEXT, artist TEXT,
                 bpm REAL, camelot TEXT, moment TEXT, ambiance TEXT, genre TEXT)""")
    open_features(c); return c

def test_left_join_keeps_unanalysed_track():
    c = _db()
    c.execute("INSERT INTO tracks VALUES ('t1','A','x',128.0,'8A',NULL,NULL,'techno')")
    cands = load_candidates(c, "av1")
    assert len(cands) == 1 and cands[0].energy is None   # pas de features -> neutre

def test_rank_orders_and_excludes():
    c = _db()
    c.execute("INSERT INTO tracks VALUES ('good','G','x',128.0,'8A',NULL,NULL,'techno')")
    c.execute("INSERT INTO tracks VALUES ('bad','B','x',128.0,'3B',NULL,NULL,'techno')")
    c.execute("INSERT INTO tracks VALUES ('self','S','x',128.0,'8A',NULL,NULL,'techno')")
    for cid in ("good","bad","self"):
        upsert_features(c, cid, {"energy_score": 7, "analysis_version": "av1"})
    prev = Candidate(content_id="p", title=None, artist=None, bpm=128.0, camelot="8A",
                     energy=7, moment=None, ambiance=None, embedding=None)
    ranked = rank(load_candidates(c, "av1"), SlotContext(prev=prev, target_energy=7.0),
                  exclude_ids={"self"})
    ids = [r.content_id for r in ranked]
    assert ids == ["good", "bad"]        # 'self' exclu, 'good' devant 'bad'

def test_empty_after_filter_is_empty_list():
    c = _db()
    assert rank(load_candidates(c, "av1", genres=["house"]), SlotContext(prev=None, target_energy=5.0)) == []
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement in `setbuilder/candidates.py`**

`load_candidates` : `SELECT` avec `LEFT JOIN features USING(content_id)` filtré sur `features.analysis_version = ?` (via `ON` pour garder la ligne quand pas de features) ; filtres `genres`/`moments` → clauses `IN` optionnelles ; décode `muq_embedding` (BLOB float32, longueur `muq_dim`) en `np.ndarray` ou `None`. Mappe chaque ligne en `Candidate`. `rank` : `score_candidate` sur chaque candidat hors `exclude_ids`, tri `score` décroissant (tie-break stable par `content_id`).

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): candidate loader + ranked suggestions`.

---

### Task 8 : Smoke d'intégration du moteur

**Files:**
- Create: `tests/test_scoring_smoke.py`

**Interfaces:**
- Consumes: toute la chaîne (`load_candidates` → `rank`) sur un mini-cache réaliste avec embeddings.

- [ ] **Step 1: Write the smoke test**

Monte un `setbuilder.db` en mémoire avec ~5 morceaux (BPM variés, clés compatibles et non, énergies 3-9, embeddings MuQ aléatoires mais déterministes via `np.random.default_rng(0)`, dim 1024). Construit une `EnergyCurve` warm-up→peak, un `SlotContext` avec un `prev` donné et `target_energy = curve.target_at(0.4)`. Appelle `rank`. Vérifie : résultat non vide, scores dans `[0,100]`, trié décroissant, chaque `ScoreBreakdown.dimensions` contient les 5 clés avec un label non vide, et le morceau clé-compatible + BPM proche + énergie proche de la cible arrive dans le top 2.

- [ ] **Step 2: Run** — `uv run pytest tests/test_scoring_smoke.py -v` → PASS.
- [ ] **Step 3: Commit** — `test(setbuilder): end-to-end scoring smoke`.

---

## Self-Review (rempli à l'écriture)

1. **Couverture spec §4.3** : key (T1), BPM (T2), énergie vs courbe (T3+T5), proximité son/MuQ (T4), ambiance/My Tag (T5), combinaison explicable + poids ajustables (T6), candidats = toute la lib + filtres (T7). ✓ Tout couvert.
2. **Granularité des étapes** : chaque step écrit une chose vérifiable (test → échec → implémentation signée → passe → commit). ✓
3. **Cohérence des types** : `Candidate`/`SlotContext`/`ScoreBreakdown`/`Weights` définis en T6, consommés en T7/T8 avec les mêmes champs. Sous-score partout `tuple[str, float]`. ✓
4. **Review Focus** : données manquantes (T1,T2,T4,T5,T7), pas de prev (T6), position hors bornes (T3), liste vide (T7) — chaque ligne a son test. ✓
5. **Proportion** : plan ~ taille du code visé (7 petits modules purs + 1 loader), bodies remplacés par signatures + tests. ✓

## Hors périmètre (plans suivants)

- Mapping slot → position normalisée selon le mode du set (durée vs nombre de morceaux) : **plan 4** (API + modèle de set persistant).
- Feedback d'impact d'un morceau forcé sur la courbe réelle : **plan 4/5**.
- Galaxy (UMAP déjà en cache) et tracé du chemin : **plan 5** (frontend).
- Export Rekordbox : **plan 5**.
