# Set Builder — Document de conception

> Outil perso de préparation de sets DJ sur la librairie Rekordbox de Matthieu.
> Design validé en brainstorming le 2026-11-03.

## 1. Intention & pourquoi

Matthieu prépare ses sets aujourd'hui en sélectionnant un paquet de morceaux dans Rekordbox
(cues déjà posés par djcues) puis **improvise tout le déroulé en live**. En club, où il veut
une ligne de conduite, ça le fait chercher "quel morceau après quel morceau" sur le moment et
laisse peu de place à l'exécution.

L'outil doit lui permettre de **bâtir l'ossature d'un set à l'avance** : une tracklist ordonnée
qui suit une courbe d'énergie voulue, construite autour de morceaux d'ancrage, avec des
suggestions d'enchaînement. But final : arriver en club avec une colonne vertébrale, pour se
concentrer sur les transitions, les effets et la lecture de la foule — **sans tuer l'impro**, juste
en lui donnant une base solide dont il peut s'écarter.

## 2. Goals / Non-goals / Anti-goals

**Goals**
- Définir une **courbe d'énergie cible** sur la durée du set (warm-up → building → peak → main → after).
- Poser des **morceaux d'ancrage** à des positions choisies.
- **Remplir les trous** avec des suggestions classées par compatibilité (key, BPM, énergie, vibe).
- **Carte "Galaxy"** : toute la lib en nuage par proximité de son, avec le chemin du set tracé dessus.
- **Feedback d'impact** : forcer un morceau hors suggestions montre son effet sur la courbe réelle
  (saut/creux d'énergie, clash de key) sans bloquer le choix.
- **Exporter le set fini vers Rekordbox** comme playlist ordonnée (avec backup master.db).

**Non-goals**
- Pas de mixage/lecture audio dans l'outil (il prépare, il ne joue pas).
- Pas de (re)placement de cues — déjà fait par djcues.
- Pas de multi-utilisateur, pas de cloud, pas de compte. Local, mono-poste.

**Anti-goals** (échec même si ça "marche")
- Un set rigide qu'il faut jouer au métronome → l'outil doit rester une base, pas une prison.
- Réécrire ou corrompre la librairie Rekordbox (cues, grid, tags existants).
- Des suggestions "boîte noire" qu'il ne comprend pas → chaque score doit être explicable
  (pourquoi 94 % : key ✓, +1 BPM, énergie ↗).

## 3. Contraintes

- **Données source** : `~/Library/Pioneer/rekordbox/master.db` (SQLite SQLCipher), lu via
  `pyrekordbox` 0.4.4 (`Rekordbox6Database`). ~4136 morceaux. Rekordbox **doit être fermé** pour tout write.
- **Déjà disponible par morceau** : BPM, key (Camelot), My Tags (Moment: Warm-up/Building/Main/Peak/After,
  Ambiance, Session), ColorID, cues/phrases, `file_path`.
- **Fichiers audio** sur une clé USB externe (FAT32) — l'analyse audio doit résoudre `file_path`
  vers le volume monté ; gérer l'absence de la clé (lib montée ou pas).
- **Pas d'embeddings ni de mood/energy ML** dans Rekordbox → à générer (voir §4.2), une fois, en batch.
- Sécurité : **jamais de suppression**, backup auto de master.db avant chaque write (pattern djcues/reorg déjà en place).
- Bug connu FAT32 NFC/NFD sur la clé USB → réutiliser le fallback de normalisation existant.

## 4. Comment c'est fait (décisions prises)

### 4.1 Architecture — *(mon choix)*
Application **web locale mono-poste** :
- **Backend Python / FastAPI** : lit master.db via pyrekordbox, sert l'API (lib, scoring, galaxy, export),
  lance le pipeline d'analyse. Cohérent avec l'existant (`~/Documents/rekordbox/` est déjà full Python/pyrekordbox).
- **Frontend navigateur**, stylé **Claude Design System** (tokens CDS, esthétique validée sur la maquette).
- Stockage des features calculées dans une **base locale séparée** (SQLite `setbuilder.db`), **jamais dans master.db**,
  indexée par un ID stable Rekordbox (content ID). master.db reste lu seul, écrit seulement à l'export.

### 4.2 Pipeline d'analyse (le gros morceau) — *(décidé avec Matthieu)*
Passe batch unique sur les ~4136 morceaux, résultats en cache dans `setbuilder.db`. **Deux modèles** :
- **Embedding de vibe** (pour la Galaxy + dimension "proximité de son") : **MuQ** (poids open Hugging Face, PyTorch) →
  un vecteur par morceau. C'est lui qui porte la similarité de vibe.
- **Genre + mood + énergie** : **Essentia `discogs-effnet-bs64`** (TensorFlow, CPU) → têtes MTG
  (`mood_happy/sad/party/relaxed/aggressive`) + `valence`/`arousal` + genre multi-label
  → **energy_score 1-10** (formule combinant arousal + énergie spectrale, versionnée).
- **Galaxy 2D** : **UMAP** (`umap-learn`, `n_neighbors≈15`) sur les embeddings **MuQ**, coords en cache.
- **Stack impliqué** : PyTorch + poids MuQ (HF) **et** essentia-tensorflow. Plus lourd qu'EffNet seul, assumé
  pour la qualité. Faisabilité arm64 à vérifier en phase plan (cf. §6, mon ressort).
- Idempotent : ne réanalyse que les nouveaux morceaux (hash + content ID), comme les scripts reorg existants.

### 4.3 Scoring des suggestions — *(mon choix, explicable)*
Candidats = **toute la librairie** (décision Matthieu : pas de crate pré-scopé obligatoire ; des filtres
genre/My Tag restent dispo pour réduire le bruit, mais le défaut est la lib entière).
Pour un slot donné (contexte = morceau précédent + cible d'énergie locale), score 0-100 combinant :
- **Key** : compatibilité harmonique Camelot (même clé / ±1 / relative / incompatible) — pondération forte.
- **BPM** : proximité au morceau précédent (fenêtre ±~6 %, pénalité au-delà).
- **Énergie** : écart entre l'énergie du candidat et la **cible de la courbe** à cette position.
- **Proximité de son** : distance cosine dans l'espace embedding **MuQ** (continuité de vibe).
- **Ambiance / My Tag** : bonus si cohérent avec le moment/ambiance du slot.
Chaque suggestion expose le **détail** (key ✓, +1 BPM, énergie ↗) — pas de score opaque. Poids ajustables.

### 4.4 Modèle de set & écran — *(set flexible, décision Matthieu)*
Un set se définit **au choix par durée** (ex. 90 min) **ou par nombre de morceaux** (ex. 12), réglé par set.
- Mode **durée** : l'axe X de la courbe = temps ; chaque slot est positionné par la **durée cumulée** des morceaux
  en amont (morceaux de longueurs variables) ; la cible d'énergie est lue à ce temps.
- Mode **nombre** : l'axe X = index de slot (N slots réguliers) ; cible d'énergie par index.
- Le modèle de données stocke les deux (slot `position` + `start_time_s` calculé) ; le rendu courbe/timeline
  bascule selon le mode du set.

Écran unique (validé en maquette v2), de haut en bas : header set (mode durée/nb, slots) ·
**courbe énergie cible vs réelle** + bandeau d'alerte si décrochage ·
**timeline** horizontale des slots (ancres colorées, slot vide sélectionné, morceau forcé en rouge) ·
**suggestions** du slot sélectionné (classées, explicables) · **Galaxy** (nuage par proximité, chemin du set tracé,
morceau forcé repéré hors flux).

### 4.5 Export Rekordbox — *(mon choix)*
Set fini → **playlist Rekordbox ordonnée** écrite dans master.db via pyrekordbox, Rekordbox fermé,
**backup auto** avant write (pattern existant). Nom de playlist = nom du set. Réversible (c'est juste une playlist).

## 5. Laissé au builder
- Choix FastAPI vs autre micro-serveur Python ; structure des endpoints ; build du frontend (vanilla + CDS tokens
  vs petit framework) — tant que l'esthétique CDS et l'écran §4.4 sont respectés.
- Détails UX d'édition de la courbe (drag des points) et de réordonnancement des slots (drag & drop).
- Formule exacte `energy_score` et poids de scoring par défaut (doivent être ajustables, documentés).
- Mécanique de cache/invalidation de `setbuilder.db`.
- Gestion fine clé USB absente (mode dégradé lecture seule des features en cache).

## 6. Décisions résolues (builder-check du 2026-11-03)
- **Moteur son** : MuQ (vibe) + EffNet (genre/mood). *(choix Matthieu)*
- **Périmètre** : suggestions + galaxy sur **toute la lib**, filtres optionnels. *(choix Matthieu)*
- **Modèle de set** : **flexible**, durée OU nombre de morceaux par set. *(choix Matthieu)*
- **Hébergement** : **local Mac** d'abord, archi prête pour l'hybride VPS en phase 2. *(choix Matthieu)*
- **Couverture audio** : analyse depuis la clé USB (lib complète) ; morceaux introuvables = grisés galaxy /
  hors suggestions, jamais bloquants. *(mon choix)*
- **Essentia + MuQ sur Apple Silicon** : ✅ **VÉRIFIÉ par spike le 2026-11-03** (voir §9).
- **Export** : réutilise le write-path prouvé de `reorg_2026_09.py` (backup → create_playlist → add_to_playlist
  → commit). Risque faible. *(confirmé builder-check)*

## 7. Vérification (fin de build)
- Lib Rekordbox lue sans jamais être modifiée hors export ; backup présent avant tout write.
- Passe d'analyse complète sur un petit lot → features + embedding + UMAP en cache, réexécutable sans doublon.
- Construire un set test (ancres + courbe), vérifier suggestions explicables, forcer un morceau → impact courbe visible.
- Export → playlist ordonnée visible dans Rekordbox, master.db intègre (ouvre sans erreur), backup restaurable.

## 9. Spike faisabilité ML (2026-11-03) — ✅ local-first validé

Testé sur le Mac de Matthieu (Apple Silicon arm64, macOS 15.7, Python 3.12.13) sur 180 s d'audio synthétique.

| Brique | Statut | Perf (180 s audio) | Extrapolation 4136 tracks |
|---|---|---|---|
| **Essentia-TensorFlow** (`essentia-tensorflow==2.1b6.dev1389`, wheel arm64 OK) | ✅ out-of-box | EffNet embedding 1,65 s, shape (180, 1280) | **~2 h CPU** mono-thread (parallélisable) |
| **MuQ** (`muq==0.1.0`) | ✅ avec pin transformers | load 3,3 s, inférence 17,66 s, hidden (1, 3000, 1024) | ~20 h CPU (à accélérer via MPS/batch, ou run de nuit) |
| **Torch** 2.15.0 | ✅ MPS dispo | — | — |

**Contrainte dure pour le plan 2** : MuQ est **incompatible avec `transformers` 5.x** (crash
`'EasyDict' object has no attribute '_attn_implementation'`). Épingler **`transformers==4.44.2`** +
**`tokenizers==0.19.1`** (confirmé : MuQ tourne avec ce pin). Isoler l'env MuQ de l'env Essentia si besoin.

**Détails techniques retenus** :
- EffNet Discogs : embedding (frames, 1280) ; modèle `discogs-effnet-bs64-1.pb` (~18 Mo) depuis essentia.upf.edu.
- MuQ-large (`OpenMuQ/MuQ-large-msd-iter`) : hidden 1024-d par frame → **mean-pool** pour un vecteur vibe par track.
- MuQ est le goulot d'étranglement du batch ; prévoir MPS et/ou batching, et un run incrémental (cache des embeddings).
