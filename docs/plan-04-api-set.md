# Set Builder — Plan 4 : API + modèle de set + feedback d'impact

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommandé) ou superpowers:executing-plans pour exécuter ce plan tâche par tâche. Les étapes utilisent des cases à cocher (`- [ ]`).

**Goal:** Un backend local qui persiste des sets flexibles (par durée OU par nombre de morceaux), remplit chaque slot via le moteur de scoring, et montre l'impact d'un morceau forcé sur la courbe — exposé en API JSON pour le futur frontend.

**Architecture:** FastAPI mono-poste sur `setbuilder.db`. Deux nouvelles couches par-dessus les plans 1-3 : (1) un *repository* de sets (tables `sets` + `set_slots`), (2) des fonctions pures de timeline (slot → position normalisée + temps de départ) et d'impact (morceau forcé → écarts courbe/key/BPM). L'API câble lib + galaxy + sets + suggestions + impact ; elle réutilise `scoring.rank` et `curve.EnergyCurve` tels quels, sans les dupliquer. Lecture seule de master.db ici ; l'export arrive au plan 5.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic (modèles d'API), httpx + `TestClient` (tests), sqlite3. Tests `uv run pytest`.

**Spec:** `projets/dj-hotcues/setbuilder-design.md` (§4.1 archi, §4.4 modèle de set & écran, §4.3 scoring déjà fait au plan 3). Copie repo : `docs/design.md`.

## Global Constraints

- **Réutilise les plans 1-3** : `scoring.score_candidate`/`rank`, `scoring.Candidate`/`SlotContext`, `curve.EnergyCurve`, `candidates.load_candidates`, `cache.open_cache`, `features_cache`. Ne jamais recopier leur logique.
- **Sets dans `setbuilder.db`** : nouvelles tables `sets` + `set_slots`. Jamais d'écriture dans master.db (l'export playlist est au plan 5).
- **Set flexible** : un set a un `mode` ∈ {`duration`, `count`} et une cible `target` (secondes si durée, nb de slots si nombre). Le mapping slot→position normalisée [0,1] dépend du mode (Tâche 2).
- **Feedback non bloquant** : forcer un morceau hors suggestions renvoie un `ImpactReport` structuré (écart d'énergie à la cible, clash de key avec voisins, saut de BPM) mais n'empêche jamais le placement.
- **Explicabilité conservée** : les suggestions renvoyées par l'API portent le `ScoreBreakdown` complet (score + détail par dimension) du plan 3.
- **API locale** : pas d'auth, CORS ouvert sur `localhost` pour le front (plan 5). Réponses JSON via modèles Pydantic.
- **`start_time_s` calculé, jamais stocké** (évite le rance) : recomputé à la lecture depuis les durées des morceaux placés.
- Pins ajoutés : `fastapi`, `uvicorn`, `httpx` (dans le groupe `dev` pour httpx/TestClient, `fastapi`/`uvicorn` en dépendance principale).

## Review Focus

- **Set à 0 ou 1 slot** : `slot_position` ne divise jamais par zéro (N=1 → position 0.0) → Tâche 2.
- **Mode `duration` avec slots vides** : la durée cumulée ignore les slots vides (durée inconnue = 0) et reste monotone → Tâche 2/3.
- **Slot index hors bornes** dans l'API : 404 explicite, pas d'exception 500 → Tâche 7/8.
- **Suggestions sans features** (lib pas encore analysée) : `rank` renvoie un classement neutre, l'API répond 200 avec les breakdowns → Tâche 5/8.
- **Morceau forcé sans features ou sans voisin** : `forced_impact` calcule ce qu'il peut et marque le reste `n/a`, jamais d'erreur → Tâche 6.

---

### Task 1 : Schéma + repository de sets

**Files:**
- Create: `setbuilder/sets_repo.py`
- Test: `tests/test_sets_repo.py`

**Interfaces:**
- Consumes: une connexion `sqlite3` ouverte par `cache.open_cache`.
- Produces:
  - dataclasses `Slot(position: int, content_id: str | None, is_anchor: bool, is_forced: bool)` et `SetRecord(set_id: str, name: str, mode: str, target: float, curve_points: list[tuple[float, float]], analysis_version: str, slots: list[Slot])`.
  - `open_sets(cache) -> None` (crée les tables).
  - `create_set(cache, name, mode, target, curve_points, analysis_version, n_slots) -> str` (retourne `set_id`, crée `n_slots` slots vides).
  - `get_set(cache, set_id) -> SetRecord | None`, `list_sets(cache) -> list[SetRecord]`, `delete_set(cache, set_id) -> None`.
  - `place_track(cache, set_id, position, content_id, *, is_anchor=False, is_forced=False) -> None`, `clear_slot(cache, set_id, position) -> None`.

- [ ] **Step 1: Write the failing test**

```python
import sqlite3
from setbuilder.sets_repo import open_sets, create_set, get_set, list_sets, delete_set, place_track, clear_slot

def _c(): c = sqlite3.connect(":memory:"); open_sets(c); return c

def test_create_and_read_roundtrip():
    c = _c()
    sid = create_set(c, "Club 90", "count", 12, [(0.0,2.0),(0.5,9.0),(1.0,4.0)], "av1", n_slots=12)
    rec = get_set(c, sid)
    assert rec.name == "Club 90" and rec.mode == "count" and len(rec.slots) == 12
    assert all(s.content_id is None for s in rec.slots)
    assert rec.curve_points[1] == (0.5, 9.0)

def test_place_and_clear():
    c = _c()
    sid = create_set(c, "x", "count", 3, [(0.0,5.0)], "av1", n_slots=3)
    place_track(c, sid, 1, "trackA", is_anchor=True)
    assert get_set(c, sid).slots[1].content_id == "trackA"
    assert get_set(c, sid).slots[1].is_anchor is True
    clear_slot(c, sid, 1)
    assert get_set(c, sid).slots[1].content_id is None

def test_invalid_mode_rejected():
    import pytest
    c = _c()
    with pytest.raises(ValueError):
        create_set(c, "x", "nope", 3, [(0.0,5.0)], "av1", n_slots=3)

def test_delete_removes_set_and_slots():
    c = _c()
    sid = create_set(c, "x", "count", 2, [(0.0,5.0)], "av1", n_slots=2)
    delete_set(c, sid); assert get_set(c, sid) is None and list_sets(c) == []
```

- [ ] **Step 2: Run to verify it fails** — FAIL (module absent).
- [ ] **Step 3: Implement `setbuilder/sets_repo.py`**

Deux tables : `sets(set_id PK, name, mode, target REAL, curve_json TEXT, analysis_version, created_at)` et `set_slots(set_id, position INT, content_id, is_anchor INT, is_forced INT, PRIMARY KEY(set_id, position))`. `set_id` = `uuid4().hex`. `mode` validé contre `{"duration","count"}` (sinon `ValueError`). `curve_points` sérialisé en JSON. `get_set` lit les deux tables et reconstruit `SetRecord` (slots triés par position). `delete_set` supprime les deux. Booléens stockés en 0/1.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): set + slots repository`.

---

### Task 2 : Position normalisée du slot (durée vs nombre)

**Files:**
- Create: `setbuilder/timeline.py`
- Test: `tests/test_timeline.py`

**Interfaces:**
- Produces:
  - `slot_position(index: int, n_slots: int, mode: str, durations: list[float | None], target: float) -> float` — position normalisée [0,1] du slot `index`.
  - `slot_start_times(durations: list[float | None]) -> list[float]` — temps de départ cumulé (mode durée), slot vide = durée 0.

- [ ] **Step 1: Write the failing test**

```python
from setbuilder.timeline import slot_position, slot_start_times

def test_count_mode_even_spacing():
    assert slot_position(0, 4, "count", [None]*4, 4) == 0.0
    assert slot_position(3, 4, "count", [None]*4, 4) == 1.0
    assert slot_position(1, 4, "count", [None]*4, 4) == 1/3

def test_count_single_slot_no_div_zero():
    assert slot_position(0, 1, "count", [None], 1) == 0.0

def test_duration_mode_by_cumulative_time():
    durs = [120.0, 180.0, 300.0]           # 2min, 3min, 5min
    # slot 2 commence après 120+180 = 300 s ; set cible 600 s -> 0.5
    assert slot_position(2, 3, "duration", durs, 600.0) == 0.5

def test_duration_empty_slot_counts_zero():
    durs = [120.0, None, 300.0]            # slot 1 vide -> 0 s
    assert slot_position(2, 3, "duration", durs, 600.0) == 120.0/600.0

def test_start_times_cumulative():
    assert slot_start_times([120.0, None, 300.0]) == [0.0, 120.0, 120.0]
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement `setbuilder/timeline.py`**

`slot_position` : mode `count` → `index/(n_slots-1)` si `n_slots>1` sinon `0.0`. Mode `duration` → somme des durées (slot vide = 0) des slots **avant** `index`, divisée par `target`, clampée `[0,1]`. `slot_start_times` : préfixes cumulés (slot vide ajoute 0), longueur = nb de slots.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): slot position mapping (duration/count)`.

---

### Task 3 : Contexte de slot (morceau précédent + cible d'énergie)

**Files:**
- Create: `setbuilder/slot_context.py`
- Test: `tests/test_slot_context.py`

**Interfaces:**
- Consumes: `sets_repo.SetRecord`, `candidates.load_candidates`, `curve.EnergyCurve`, `timeline.slot_position`, `scoring.Candidate`/`SlotContext`.
- Produces:
  - `candidates_by_id(cache, analysis_version) -> dict[str, Candidate]`.
  - `build_slot_context(set_rec, slot_index, by_id, durations) -> SlotContext` — `prev` = le `Candidate` du dernier slot rempli **avant** `slot_index` (None si aucun), `target_energy` = courbe à la position du slot.

- [ ] **Step 1: Write the failing test**

```python
from setbuilder.slot_context import build_slot_context
from setbuilder.sets_repo import SetRecord, Slot
from setbuilder.scoring import Candidate

def _cand(cid, e): return Candidate(cid, cid, "x", 128.0, "8A", e, None, None, None)

def test_prev_is_last_filled_before_slot():
    rec = SetRecord("s","n","count",3,[(0.0,2.0),(1.0,8.0)],"av1",
                    [Slot(0,"a",True,False), Slot(1,None,False,False), Slot(2,None,False,False)])
    by_id = {"a": _cand("a",5)}
    ctx = build_slot_context(rec, 1, by_id, durations=[None,None,None])
    assert ctx.prev.content_id == "a"
    assert ctx.target_energy == rec_target(rec, 1)   # courbe à pos 0.5

def test_first_slot_has_no_prev():
    rec = SetRecord("s","n","count",2,[(0.0,5.0)],"av1",
                    [Slot(0,None,False,False), Slot(1,None,False,False)])
    ctx = build_slot_context(rec, 0, {}, durations=[None,None])
    assert ctx.prev is None
```

(helper `rec_target` : construit `EnergyCurve.from_points(rec.curve_points)` et lit `target_at(slot_position(...))` — le test le définit localement.)

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement `setbuilder/slot_context.py`**

`candidates_by_id` : indexe `load_candidates` par `content_id`. `build_slot_context` : remonte de `slot_index-1` à 0, prend le premier slot avec `content_id` renseigné et présent dans `by_id` → son `Candidate` ; `target_energy = EnergyCurve.from_points(set_rec.curve_points).target_at(slot_position(slot_index, len(slots), set_rec.mode, durations, set_rec.target))`. Pas de morceau précédent → `prev=None`. Reporte `slot_moment`/`slot_ambiance` depuis les My Tags du slot si un jour présents (sinon None).

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): slot scoring context builder`.

---

### Task 4 : Suggestions pour un slot

**Files:**
- Create: `setbuilder/suggest.py`
- Test: `tests/test_suggest.py`

**Interfaces:**
- Consumes: `candidates.load_candidates`/`rank`, `slot_context.build_slot_context`/`candidates_by_id`, `sets_repo`.
- Produces: `suggestions_for_slot(cache, set_rec, slot_index, *, weights=DEFAULT_WEIGHTS, limit=20) -> list[ScoreBreakdown]` — classement du slot, excluant les morceaux déjà placés dans le set.

- [ ] **Step 1: Write the failing test** (monte cache lib+features, un set, vérifie que le top exclut les morceaux déjà posés et respecte la limite)

```python
# insère 3 tracks + features ; pose 'a' en slot 0 ; demande suggestions slot 1
# -> 'a' absent du classement, résultats triés, limite respectée
def test_suggestions_exclude_placed_and_limit():
    ...
    sugg = suggestions_for_slot(cache, rec, 1, limit=2)
    assert all(s.content_id != "a" for s in sugg)
    assert len(sugg) <= 2
    assert [s.score for s in sugg] == sorted([s.score for s in sugg], reverse=True)
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement `setbuilder/suggest.py`**

Charge `by_id` une fois, calcule `durations` depuis les tracks placés, construit le `SlotContext` (Tâche 3), appelle `rank(load_candidates(...), ctx, weights, exclude_ids=<ids déjà placés>)`, tronque à `limit`.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): per-slot suggestions`.

---

### Task 5 : Feedback d'impact d'un morceau forcé

**Files:**
- Create: `setbuilder/impact.py`
- Test: `tests/test_impact.py`

**Interfaces:**
- Consumes: `harmony.camelot_compat`, `bpm.bpm_compat`, `fit.energy_fit`, `scoring.Candidate`, `curve.EnergyCurve`, `timeline.slot_position`.
- Produces:
  - dataclass `ImpactReport(energy: tuple[str, float], key_prev: tuple[str, float], key_next: tuple[str, float], bpm_prev: tuple[str, float], warnings: list[str])`.
  - `forced_impact(forced: Candidate, prev: Candidate | None, next_: Candidate | None, target_energy: float) -> ImpactReport`.

- [ ] **Step 1: Write the failing test**

```python
from setbuilder.impact import forced_impact
from setbuilder.scoring import Candidate

def _c(cid, bpm, cam, e): return Candidate(cid, cid, "x", bpm, cam, e, None, None, None)

def test_clash_and_energy_dip_warned():
    forced = _c("f", 150.0, "3B", 2)     # clash key + loin de la cible
    prev   = _c("p", 128.0, "8A", 7)
    rep = forced_impact(forced, prev, None, target_energy=8.0)
    assert rep.key_prev[1] == 0.0        # clash
    assert rep.energy[1] < 0.3           # 2 vs cible 8
    assert any("key" in w.lower() for w in rep.warnings)
    assert any("énergie" in w.lower() for w in rep.warnings)

def test_no_neighbour_is_na_not_error():
    rep = forced_impact(_c("f",128.0,"8A",7), None, None, target_energy=7.0)
    assert rep.key_prev == ("key inconnue", 0.5)
    assert rep.warnings == []            # rien d'alarmant

def test_missing_features_na():
    forced = Candidate("f","f","x",None,None,None,None,None,None)
    rep = forced_impact(forced, _c("p",128.0,"8A",7), None, target_energy=7.0)
    assert rep.energy == ("énergie n/a", 0.5)
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement `setbuilder/impact.py`**

Réutilise les dimensions du plan 3 : `energy_fit(forced.energy, target)`, `camelot_compat(prev.camelot, forced.camelot)` et `camelot_compat(forced.camelot, next_.camelot)`, `bpm_compat(prev.bpm, forced.bpm)`. Construit `warnings` : ajoute un message quand un sous-score applicable passe sous un seuil (clash key < 0.3, énergie < 0.4, BPM < 0.4), avec le détail lisible. Dimensions n/a (voisin absent, feature absente) n'émettent pas de warning.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): forced-track impact report`.

---

### Task 6 : App FastAPI + endpoints lib / galaxy / sets

**Files:**
- Create: `setbuilder/api.py`
- Modify: `pyproject.toml` (deps `fastapi`, `uvicorn` ; `httpx` en dev)
- Test: `tests/test_api_sets.py`

**Interfaces:**
- Produces: `create_app(db_path: str) -> FastAPI` avec :
  - `GET /library` → liste des tracks (depuis `tracks`, + `energy_score`/`top_genre` si features).
  - `GET /galaxy` → points UMAP (`content_id, umap_x, umap_y`) depuis la table `galaxy`.
  - `POST /sets` (name, mode, target, curve_points, n_slots) → `{set_id}` ; `GET /sets`, `GET /sets/{id}`, `DELETE /sets/{id}`.
  - `PUT /sets/{id}/slots/{pos}` (content_id, is_anchor, is_forced) → slot mis à jour ; `DELETE /sets/{id}/slots/{pos}` → vide le slot.

- [ ] **Step 1: Write the failing test** (`TestClient`, db temporaire)

```python
from fastapi.testclient import TestClient
from setbuilder.api import create_app

def test_set_crud_via_api(tmp_path):
    # prépare un setbuilder.db avec tables tracks/features/galaxy vides
    client = TestClient(create_app(str(db)))
    r = client.post("/sets", json={"name":"Club","mode":"count","target":3,
                                   "curve_points":[[0,2],[1,8]],"n_slots":3})
    sid = r.json()["set_id"]; assert r.status_code == 200
    assert client.get(f"/sets/{sid}").json()["slots"] == 3 or len(...slots) == 3
    client.put(f"/sets/{sid}/slots/0", json={"content_id":"a","is_anchor":True})
    assert client.get(f"/sets/{sid}").json()["slots"][0]["content_id"] == "a"
    assert client.get("/sets/doesnotexist").status_code == 404
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement `setbuilder/api.py`**

`create_app` ouvre le cache (connexion par requête, `check_same_thread=False` ou ouverture à la demande), monte CORS `allow_origins=["*"]` pour le dev local, modèles Pydantic pour les corps. Les routes délèguent à `sets_repo` ; `set_id` inconnu → `HTTPException(404)`. `GET /sets/{id}` sérialise `SetRecord` (slots + `start_time_s` calculé via `timeline.slot_start_times`).

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): FastAPI app with library/galaxy/sets endpoints`.

---

### Task 7 : Endpoints suggestions + forçage avec impact

**Files:**
- Modify: `setbuilder/api.py`
- Test: `tests/test_api_suggest.py`

**Interfaces:**
- Produces:
  - `GET /sets/{id}/slots/{pos}/suggestions?limit=` → liste de `{content_id, score, dimensions}`.
  - `POST /sets/{id}/slots/{pos}/force` (content_id) → place le morceau en `is_forced=True` et renvoie `{slot, impact: ImpactReport}`.

- [ ] **Step 1: Write the failing test** (db avec quelques tracks+features, un set ; vérifie suggestions non vides et forçage qui renvoie un impact)

```python
def test_suggestions_and_force_impact(tmp_path):
    client = ...
    sugg = client.get(f"/sets/{sid}/slots/1/suggestions?limit=5").json()
    assert isinstance(sugg, list)
    for s in sugg: assert set(s["dimensions"]) == {"key","bpm","energy","vibe","ambiance"}
    r = client.post(f"/sets/{sid}/slots/1/force", json={"content_id":"clash"})
    assert r.status_code == 200
    assert "impact" in r.json() and "warnings" in r.json()["impact"]
    # le morceau est bien placé et marqué forcé
    assert client.get(f"/sets/{sid}").json()["slots"][1]["is_forced"] is True
```

- [ ] **Step 2: Run to verify it fails** — FAIL.
- [ ] **Step 3: Implement les deux routes dans `setbuilder/api.py`**

`suggestions` → `suggest.suggestions_for_slot`, sérialise les `ScoreBreakdown`. `force` → calcule le `prev`/`next_` via `slot_context` (voisins remplis), place le morceau (`place_track ... is_forced=True`), renvoie `forced_impact(...)` sérialisé. Slot/ set hors bornes → 404.

- [ ] **Step 4: Run to verify it passes** — PASS.
- [ ] **Step 5: Commit** — `feat(setbuilder): suggestion + forced-track endpoints`.

---

### Task 8 : Smoke d'intégration API bout-en-bout

**Files:**
- Create: `tests/test_api_smoke.py`

**Interfaces:**
- Consumes: toute la chaîne via `TestClient`.

- [ ] **Step 1: Write the smoke test**

Prépare un `setbuilder.db` temporaire (via `cache.open_cache` + `features_cache.open_features`) avec ~6 tracks (BPM/clés/énergies variés, embeddings déterministes, un point galaxy chacun). Scénario : `POST /sets` (mode durée, courbe warm-up→peak→after) ; `PUT` d'une ancre en slot 0 ; `GET .../suggestions` sur un slot vide → top non vide et explicable ; `POST .../force` d'un morceau clashant → `impact.warnings` non vide ; `GET /sets/{id}` final → l'ancre et le morceau forcé sont bien là avec leurs flags, `start_time_s` croissant. `GET /galaxy` → 6 points.

- [ ] **Step 2: Run** — `uv run pytest tests/test_api_smoke.py -v` → PASS.
- [ ] **Step 3: Commit** — `test(setbuilder): end-to-end API smoke`.

---

## Self-Review (rempli à l'écriture)

1. **Couverture spec §4.4** : modèle de set flexible durée/nombre (T1 stockage, T2 mapping position), ancres + slots (T1, T6), suggestions par slot explicables (T4, T7), feedback morceau forcé sur la courbe (T5, T7), écran alimenté par lib/galaxy/sets/suggestions/impact (T6, T7). Export = plan 5 (hors périmètre, annoncé). ✓
2. **Granularité** : chaque step écrit une chose vérifiable (test → échec → implémentation → passe → commit). ✓
3. **Cohérence des types** : `SetRecord`/`Slot` (T1) consommés par T3/T4/T6/T7 ; `SlotContext`/`Candidate`/`ScoreBreakdown` réutilisés du plan 3 sans redéfinition ; `ImpactReport` (T5) sérialisé en T7. ✓
4. **Review Focus** : N=1 (T2), slots vides en mode durée (T2/T3), index hors bornes (T6/T7), suggestions sans features (T4/T7), forcé sans voisin/feature (T5) — chacun a son test. ✓
5. **Proportion** : plan ≈ taille du code visé (5 modules + API + 3 fichiers de tests), bodies remplacés par signatures + assertions. ✓

## Hors périmètre (plan 5)

- Frontend (Claude Design System) : écran set, courbe cible vs réelle, timeline drag & drop, panneau suggestions, Galaxy 2D + tracé du chemin.
- Export Rekordbox : playlist ordonnée via pyrekordbox, backup auto, Rekordbox fermé (§4.5).
- Édition de la courbe à la souris (drag des points) et réordonnancement des slots.
