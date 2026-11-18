# Set Builder — Plan 1 : Fondation données

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Snapshoter la librairie Rekordbox dans un cache local `setbuilder.db` (séparé, jamais master.db), keyé par content ID, avec statut de résolution des fichiers audio.

**Architecture:** Package Python `setbuilder`. Lit `master.db` en lecture seule via pyrekordbox (Rekordbox fermé), mappe chaque morceau (BPM, key→Camelot, My Tags, file_path, durée, présence cues/phrases), résout le fichier audio sur le volume monté, et upsert dans un SQLite local idempotent. CLI `setbuilder sync`.

**Tech Stack:** Python 3.12, uv, pyrekordbox 0.4.4 (`Rekordbox6Database`), sqlite3 (stdlib), pytest.

**Spec:** `projets/dj-hotcues/setbuilder-design.md` (ce plan implémente §3 données, §4.1 archi, §4.2 cache, et la base du modèle de set §4.4).

## Global Constraints
- master.db : **lecture seule** dans ce plan ; aucun write. Rekordbox fermé pour toute lecture pyrekordbox.
- Cache `setbuilder.db` **séparé**, keyé par content ID Rekordbox (string stable). Jamais de schéma dans master.db.
- Jamais de suppression de fichier.
- Fallback normalisation **NFC puis NFD** pour résoudre les chemins sur FAT32 (clé USB) — bug connu documenté.
- App locale, mono-poste, pas de réseau.
- Emplacement projet : `~/Documents/rekordbox/setbuilder/` (co-localisé avec l'outillage rekordbox existant).

## Review Focus
- **Clé USB absente / fichier introuvable** : `sync` doit réussir et marquer `file_status="missing"`, jamais crasher — testé Task 5.
- **Chemin accentué NFC vs NFD** sur le volume : résolution doit tenter les deux — testé Task 4.
- **Key Rekordbox inconnue/vide** : conversion Camelot renvoie `None`, pas d'exception — testé Task 2.
- **Deuxième `sync`** (ré-exécution) : upsert idempotent, zéro doublon, mise à jour des champs changés — testé Task 5.
- **Morceau sans My Tag / sans durée** : mappé avec champs nuls, pas d'exception — testé Task 3.

---

### Task 1 : Scaffold + schéma cache

**Files:**
- Create: `~/Documents/rekordbox/setbuilder/pyproject.toml`, `setbuilder/__init__.py`, `setbuilder/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Produces: `open_cache(path: str) -> sqlite3.Connection` (crée le schéma si absent), table `tracks(content_id TEXT PRIMARY KEY, title, artist, album, bpm REAL, camelot TEXT, rb_key TEXT, moment TEXT, ambiance TEXT, genre TEXT, file_path TEXT, file_status TEXT, duration_s REAL, has_cues INT, has_phrases INT, updated_at TEXT)`.

- [ ] **Step 1: Write the failing test** — `test_open_cache_creates_schema`: ouvre un cache en fichier temp, assert que la table `tracks` existe et a les colonnes ci-dessus (via `PRAGMA table_info`).
- [ ] **Step 2: Run test, verify FAIL** — `pytest tests/test_cache.py::test_open_cache_creates_schema -v` → FAIL (module/fonction absent).
- [ ] **Step 3: Implement `open_cache(path)` dans `setbuilder/cache.py`** — `CREATE TABLE IF NOT EXISTS tracks (...)` avec les colonnes de l'Interface ; retourne la connexion.
- [ ] **Step 4: Run test, verify PASS.**
- [ ] **Step 5: Commit** — `git add` pyproject + setbuilder/ + tests ; `git commit -m "feat(setbuilder): cache schema"`.

---

### Task 2 : Conversion key → Camelot

**Files:**
- Create: `setbuilder/camelot.py`
- Test: `tests/test_camelot.py`

**Interfaces:**
- Produces: `to_camelot(rb_key: str | None) -> str | None` (ex. "Abm"→"1A", "B"→"1B", "Bb"/"A#m"… ; inconnu/None→None).

- [ ] **Step 1: Write the failing test** — `test_to_camelot`: paramétré, assert `to_camelot("Abm")=="1A"`, `to_camelot("B")=="1B"`, `to_camelot("Em")=="9A"`, `to_camelot("G")=="9B"`, `to_camelot("")==None`, `to_camelot(None)==None`, `to_camelot("??")==None`.
- [ ] **Step 2: Run test, verify FAIL.**
- [ ] **Step 3: Implement `to_camelot`** — table de correspondance des 24 clés (majeur/mineur → roue Camelot), normalise les enharmoniques (A#/Bb), tolère les notations Rekordbox ; renvoie None si non reconnu.
- [ ] **Step 4: Run test, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(setbuilder): camelot conversion"`.

---

### Task 3 : Mapping d'un morceau Rekordbox → dataclass

**Files:**
- Create: `setbuilder/rbread.py`
- Test: `tests/test_rbread.py`

**Interfaces:**
- Consumes: `to_camelot` (Task 2).
- Produces: dataclass `Track(content_id, title, artist, album, bpm, camelot, rb_key, moment, ambiance, genre, file_path, duration_s, has_cues, has_phrases)` ; `map_content(row) -> Track` où `row` est un objet contenu pyrekordbox (attributs `.ID, .Title, .ArtistName, .BPM, .Tonality/.Key, .FolderPath, .Length, .Cues, …`) ; et `read_library(db) -> Iterator[Track]`.

- [ ] **Step 1: Write the failing test** — `test_map_content_minimal`: construit un faux row (objet simple avec attributs, ou `types.SimpleNamespace`) avec BPM, key, pas de My Tag, pas de durée → assert `Track` produit, `camelot` cohérent, `moment is None`, `duration_s is None`, pas d'exception. `test_map_content_full`: row complet avec My Tags Moment/Ambiance → champs remplis.
- [ ] **Step 2: Run test, verify FAIL.**
- [ ] **Step 3: Implement `map_content(row)` et `read_library(db)`** — mappe les attributs pyrekordbox vers `Track`, convertit la key via `to_camelot`, lit les My Tags (Moment/Ambiance via DjmdSongMyTag) en tolérant l'absence, `has_cues`/`has_phrases` = bool→int. `read_library` itère `db.get_content()`.
- [ ] **Step 4: Run test, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(setbuilder): rekordbox content mapping"`.

---

### Task 4 : Résolution de fichier (NFC/NFD)

**Files:**
- Create: `setbuilder/files.py`
- Test: `tests/test_files.py`

**Interfaces:**
- Produces: `resolve_file(file_path: str) -> tuple[str | None, str]` → `(chemin_résolu_ou_None, status)` avec `status ∈ {"ok","missing"}`. Tente le chemin tel quel, puis variantes NFC et NFD du basename.

- [ ] **Step 1: Write the failing test** — `test_resolve_ok_nfc_nfd`: crée dans un tmpdir un fichier avec un nom accentué en **NFD**, appelle `resolve_file` avec le même nom en **NFC** → assert `status=="ok"` et chemin non-None. `test_resolve_missing`: chemin inexistant → `(None,"missing")`, pas d'exception.
- [ ] **Step 2: Run test, verify FAIL.**
- [ ] **Step 3: Implement `resolve_file`** — `os.path.exists` sur le chemin, sinon reconstruit avec `unicodedata.normalize("NFC"/"NFD", basename)` et re-teste ; renvoie le premier existant, sinon `(None,"missing")`.
- [ ] **Step 4: Run test, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(setbuilder): file resolution with NFC/NFD fallback"`.

---

### Task 5 : Commande `sync` (upsert idempotent)

**Files:**
- Create: `setbuilder/sync.py`, `setbuilder/__main__.py` (CLI)
- Test: `tests/test_sync.py`

**Interfaces:**
- Consumes: `open_cache` (T1), `Track`/`read_library` (T3), `resolve_file` (T4).
- Produces: `sync(tracks: Iterable[Track], cache: sqlite3.Connection) -> SyncStats` (upsert par `content_id`, set `file_status`/`file_path` résolus, `updated_at`), dataclass `SyncStats(inserted, updated, missing_files)` ; CLI `python -m setbuilder sync`.

- [ ] **Step 1: Write the failing test** — `test_sync_inserts_then_idempotent`: passe 2 `Track` (un avec fichier tmp existant, un avec chemin bidon) → assert `inserted==2`, `missing_files==1`, 2 lignes en base. Re-`sync` les mêmes → `inserted==0`, pas de doublon (toujours 2 lignes). `test_sync_updates_changed_field`: re-sync avec BPM modifié → `updated>=1` et la valeur en base est la nouvelle.
- [ ] **Step 2: Run test, verify FAIL.**
- [ ] **Step 3: Implement `sync(...)`** — pour chaque Track : `resolve_file`, `INSERT ... ON CONFLICT(content_id) DO UPDATE SET ...`, compte inserted/updated via `changes()`/pré-check, `updated_at=now`. `__main__` ouvre master.db (pyrekordbox), `read_library`, `sync`, affiche les stats ; refuse si Rekordbox tourne (message clair).
- [ ] **Step 4: Run test, verify PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat(setbuilder): idempotent library sync + CLI"`.

---

## Self-review
- **Spec coverage** : §3 données (BPM/key/MyTags/file_path/durée/cues) → T3 ; §4.1 cache local séparé → T1 ; résolution fichiers multi-volume/USB → T4+T5 ; Camelot (base scoring §4.3) → T2. Pipeline ML (§4.2), scoring (§4.3), API/front (§4.4), export (§4.5) = **plans suivants**, hors scope ici.
- **Review Focus** : clé absente→T5, NFC/NFD→T4, key invalide→T2, ré-sync→T5, champs nuls→T3. Couverts.
- **Type consistency** : `Track`/`content_id`/`to_camelot`/`resolve_file`/`open_cache` cohérents entre tasks.
- **Proportion** : plan ~ signatures + tests, pas de corps de fonction transcrit. OK.
