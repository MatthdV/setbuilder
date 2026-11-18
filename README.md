# setbuilder

A local web app that helps a DJ plan the backbone of a set before playing it, on top of an existing
[Rekordbox](https://rekordbox.com) library.

You draw a target energy curve, pin anchor tracks at chosen positions, and the app fills the gaps
with ranked suggestions (key, BPM, energy, vibe). The finished set is exported back to Rekordbox as an
ordered playlist.

I use it to prepare my own sets. It is meant for DJs who already organise their music in Rekordbox and
want a starting structure they can deviate from, not a rigid script.

## Features

- **Energy curve**: set a target curve over the length of the set (warm-up, building, peak, main, after).
- **Anchor tracks**: lock tracks at specific slots and build the rest around them.
- **Ranked suggestions**: candidates scored by harmonic compatibility (Camelot keys), BPM distance,
  energy and audio similarity, so every score can be explained.
- **Galaxy map**: the whole library as a cloud laid out by how tracks sound, with the set path drawn on top.
- **Impact feedback**: forcing a track outside the suggestions shows its effect on the actual curve
  (energy jump or dip, key clash) without blocking the choice.
- **Audio preview** with seek, for auditioning a candidate in place.
- **Export to Rekordbox** as an ordered playlist, with an automatic backup of the Rekordbox database first.

## Built with

- Python 3.12, FastAPI, SQLite
- [pyrekordbox](https://github.com/dylanljones/pyrekordbox) to read and write the Rekordbox library
- [Essentia](https://essentia.upf.edu) (genre, mood, energy) and MuQ (audio embeddings), with UMAP for the map
- Plain JavaScript front end served by the local backend, no build step
- pytest for the test suite

## Safety

- The Rekordbox database is read through pyrekordbox. The analysis results live in a separate
  `setbuilder.db` file and never touch `master.db`.
- Exporting writes to `master.db`: Rekordbox must be closed, and a backup is created before every write.
- The server only listens on `127.0.0.1` and is single-user. There is no cloud and no account.

## Getting started

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), macOS with Rekordbox 6 installed.

```bash
git clone https://github.com/MatthdV/setbuilder.git
cd setbuilder
uv sync --extra rekordbox
uv run python -m setbuilder sync       # reads your Rekordbox library into setbuilder.db
```

Optional: audio analysis (genre, mood, energy, embeddings, map). It downloads model weights on the first run.

```bash
uv sync --extra analysis
uv run python scripts/smoke_analysis.py   # smoke test on synthetic audio
uv run python -m setbuilder analyze
```

Notes on the analysis step:

- Pinned versions are required: `transformers==4.44.2` and `tokenizers==0.19.1` (MuQ fails with transformers 5.x).
- It is incremental: a track already analysed with the same `analysis_version` is skipped, and a missing
  audio file is ignored.
- MuQ is the bottleneck (about 15 to 20 seconds per 3-minute track on CPU), so run it overnight on a large
  library. `SETBUILDER_DEVICE=mps` tries Apple Silicon acceleration (not the default).
- Offline, the command stops with a clear message. Model files go to `~/.cache/setbuilder/models`
  (override with `SETBUILDER_MODELS`).

Run the app on macOS with `./setbuilder.command`, which starts the local server and opens a window on
http://127.0.0.1:8000/.

## Tests

```bash
uv run pytest
```

The tests need neither the `analysis` extra nor a Rekordbox install: no model is loaded and they use
stand-in data.

## Project layout

```
setbuilder/   backend: scoring, suggestions, energy curve, Camelot logic, analysis pipeline, API, export
web/          front end (library, timeline, suggestions, galaxy map, player)
tests/        pytest suite
docs/         design document and implementation plans
scripts/      smoke script for the analysis pipeline
```

## Status

Work in progress, used on my own library. The design document and the four implementation plans
(data foundation, analysis pipeline, scoring, API and sets) are in [`docs/`](docs).

## License

[MIT](LICENSE). Essentia, MuQ and the other optional dependencies have their own licenses; check them
before redistributing a build that bundles them.
