# Japanese Reader + SRS

A **local-first desktop application** for reading Japanese text with furigana and building vocabulary through spaced repetition. Paste or import Japanese articles, read them with per-kanji furigana and click-to-translate, auto-collect new words deduplicated by lemma, and review them with the FSRS algorithm.

Built with Python 3.11+, pywebview for the native desktop shell, and FastAPI as the local engine.

## Features

- **Furigana reader** — Paste Japanese text and read it with per-kanji aligned furigana (`<ruby>` rendering). Click any word to see its hiragana reading and English meanings.
- **Vocabulary collection** — Save words from the reader to a personal, searchable word list. Words are deduplicated by dictionary form (lemma), so `食べた`, `食べます`, and `食べる` all map to a single entry.
- **Known-word highlighting** — Already-saved words are visually marked in the reader so your eye is drawn to genuinely new vocabulary.
- **Spaced repetition (FSRS)** — Review saved vocabulary with the modern FSRS algorithm. Cards are scheduled based on your performance history (Again/Hard/Good/Easy), with review logs stored from day one for later parameter optimization.
- **FSRS parameter optimization** — After accumulating review history, the scheduler adapts to your memory patterns by tuning FSRS parameters from your logged reviews.
- **Study statistics** — Dashboard showing accuracy, total reviews, and reviews per day, computed from your review log history.
- **Anki export** — Export your vocabulary deck as a `.apkg` file (via genanki) for review on your phone in real Anki.
- **Desktop packaging** — PyInstaller spec for building a double-clickable binary on Windows and Linux, with dictionaries bundled as data files.

## Architecture

```
app.py                  # pywebview launcher (native window + uvicorn on 127.0.0.1)
server/
  main.py               # FastAPI app — all HTTP endpoints
  analyze.py            # Tokenizer wrapper, Token dataclass, analyze() pipeline
  dictionary.py         # jamdict lemma → English meanings lookup
  render.py             # Furigana <ruby> rendering with per-kanji alignment
  db.py                 # SQLite schema (texts, vocab, cards, review_logs) + CRUD
  scheduler.py          # FSRS review wrapper + parameter optimization
  stats.py              # Study statistics computation
  export.py             # genanki .apkg export
  resources.py          # Resource path resolver (dev vs PyInstaller frozen)
  importer/             # (Planned) Import tiers: paste, URL fetch, DOM import
web/
  index.html            # Reader page — paste text, analyze, read with furigana
  reader.js             # Reader logic — /analyze fetch, popover, save-word
  vocab.html / vocab.js # Searchable vocabulary list
  review.html / review.js # SRS review UI — show/reveal + rating buttons
  stats.html / stats.js # Study statistics dashboard
  style.css             # Shared styles
tests/                  # pytest suite (48 tests)
doc/
  adr-001-architecture.md # Architecture decision record
```

### Data flow

```
Raw Japanese text
  → SudachiPy tokenizer (surface, lemma, katakana reading, POS)
  → jaconv kata→hira conversion (single boundary)
  → jamdict lemma lookup (English glosses)
  → Token {surface, reading_hiragana, lemma, meanings, pos, known}
  → FastAPI JSON response
  → HTML <ruby> furigana rendering in pywebview
```

### Key design decisions

- **Lemma-based deduplication** — `vocab.lemma` is `UNIQUE` in SQLite. All inflected forms of a word resolve to a single dictionary entry.
- **Reading normalization** — Katakana-to-hiragana conversion happens exactly once inside `analyze()`. Nothing downstream ever sees katakana.
- **Localhost only** — FastAPI binds to `127.0.0.1`. This is a personal app, never a public server.
- **MIT-licensed SRS** — Uses the `fsrs` package (MIT). Never uses Anki's AGPL source code. JMdict data is CC BY-SA.
- **Review logging from day one** — `review_logs` table is populated from the first review, enabling FSRS parameter optimization later.

### Database schema

| Table | Purpose |
|---|---|
| `texts` | Stored articles (title, source_type, raw_text, cached analysis) |
| `vocab` | Word list deduplicated by lemma (reading, meaning, POS, status, seen/text counts) |
| `cards` | FSRS scheduling state per vocab entry (state, stability, difficulty, due, last_review) |
| `review_logs` | Every review rating + timestamp (drives stats and FSRS optimization) |

## Tech stack

| Concern | Library | License |
|---|---|---|
| Tokenizer | SudachiPy + sudachidict_core | Apache-2.0 |
| Dictionary | jamdict + jamdict-data | MIT (JMdict data: CC BY-SA) |
| Kana conversion | jaconv | MIT |
| Spaced repetition | fsrs (py-fsrs) | MIT |
| Article extraction | trafilatura | Apache-2.0 |
| Backend API | FastAPI + uvicorn | MIT |
| Desktop shell | pywebview | BSD |
| Anki export | genanki | MIT |
| Packaging | PyInstaller | GPL-with-exception (output is yours) |

## Getting started

### Prerequisites

- Python 3.11 or later
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd japanese-learning-app

# Install dependencies (using uv)
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"
```

### Running the app

```bash
python app.py
```

This starts the FastAPI server on `127.0.0.1:8764` and opens a native pywebview window with the reader.

### Running tests

```bash
pytest -q
```

There are currently 48 tests covering tokenization, dictionary lookup, furigana rendering, database operations, FSRS scheduling, API endpoints, statistics, Anki export, and packaging.

### Linting

```bash
ruff check .
ruff format .
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Reader page (index.html) |
| `POST` | `/analyze` | Tokenize and annotate Japanese text → token list |
| `POST` | `/vocab` | Save a word to the vocabulary list |
| `GET` | `/vocab` | List saved vocabulary (optional `?q=` search filter) |
| `GET` | `/vocab-page` | Vocabulary list page |
| `POST` | `/triage` | Triage a word: "keep" (creates FSRS card) or "known" (suppresses future) |
| `GET` | `/review-page` | Review UI page |
| `GET` | `/review/queue` | Due cards for review (optional `?now=` timestamp) |
| `POST` | `/review/answer` | Submit a review rating (1=Again, 2=Hard, 3=Good, 4=Easy) |
| `GET` | `/stats-page` | Statistics dashboard page |
| `GET` | `/stats` | Computed study statistics (accuracy, reviews/day) |
| `GET` | `/export/apkg` | Download vocabulary as Anki .apkg file |

## Building a standalone binary

The included `app.spec` bundles the web frontend, SudachiDict, and JMdict data into a single executable:

```bash
pyinstaller app.spec
```

The built binary will be in `dist/japanese-reader`. Resource paths are resolved at runtime via `server/resources.py`, which detects whether the app is running from source or from a PyInstaller bundle (`sys._MEIPASS`).

## Project status

The project follows a phased TDD roadmap defined in [ROADMAP.md](ROADMAP.md). Current status:

- **Phase 0** — Foundations & spikes (tokenizer, dictionary, ADR)
- **Phase 1** — Analysis engine (tokenize, kana conversion, dictionary lookup, analyze pipeline, caching)
- **Phase 2** — Reader UI (API endpoint, furigana rendering, pywebview shell, word popover)
- **Phase 3** — Vocabulary storage (schema, upsert dedupe, save endpoint, known-word styling)
- **Phase 5** — Spaced repetition (FSRS schema, scheduler, card persistence, review UI, triage-to-card)
- **Phase 6** — Polish & packaging (per-kanji furigana, FSRS optimization, stats, Anki export, PyInstaller)

Phase 4 (import tiers: paste intake, POS filter, candidate collection, URL fetch, DOM import) is planned but not yet implemented.
