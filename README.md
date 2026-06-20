# Japanese Reader + SRS

A **local-first desktop application** for reading Japanese text with furigana and building vocabulary through spaced repetition. Paste or import Japanese articles, read them with per-kanji furigana and click-to-translate, auto-collect new words deduplicated by lemma, and review them with the FSRS algorithm.

Built with Python 3.11+, pywebview for the native desktop shell, and FastAPI as the local engine.

## Features

- **Furigana reader** — Paste Japanese text and read it with per-kanji aligned furigana (`<ruby>` rendering). Click any word to see its hiragana reading and English meanings.
- **Vocabulary collection** — Save words from the reader to a personal, searchable word list. Words are deduplicated by dictionary form (lemma), so `食べた`, `食べます`, and `食べる` all map to a single entry.
- **Known-word highlighting** — Already-saved words are visually marked in the reader so your eye is drawn to genuinely new vocabulary.
- **Spaced repetition (FSRS)** — Review saved vocabulary with the modern FSRS algorithm. Cards are scheduled based on your performance history (Again/Hard/Good/Easy), with review logs stored from day one for later parameter optimization.
- **FSRS parameter optimization** — After accumulating review history, the scheduler adapts to your memory patterns by tuning FSRS parameters from your logged reviews.
- **Offline quiz engine** — Auto-generated multiple-choice quizzes from your own vocabulary. Three quiz types: **reading** (漢字読み — pick the correct hiragana for a kanji word), **meaning recall** (pick the English meaning), and **cloze** (文脈規定 — fill in the blank in a real sentence from your imported texts). A **mixed mode** randomly cycles through types. Distractors are same-POS and frequency-weighted using JMdict priority tags for plausible, level-matched wrong answers. Quiz results can optionally feed into FSRS so study effort counts toward spaced repetition.
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
  quiz.py               # Pure quiz logic — question generators, grading, distractor selection
  stats.py              # Study statistics computation
  export.py             # genanki .apkg export
  resources.py          # Resource path resolver (dev vs PyInstaller frozen)
  importer/             # Import tiers: paste, URL fetch, DOM import
web/
  index.html            # Reader page — paste text, analyze, read with furigana
  js/reader.js          # Reader logic — /analyze fetch, popover, save-word
  vocab.html / js/vocab.js # Searchable vocabulary list
  review.html / js/review.js # SRS review UI — show/reveal + rating buttons
  quiz.html / js/quiz.js # Quiz UI — type selector, question/answer flow
  stats.html / js/stats.js # Study statistics dashboard
  css/style.css         # Shared styles
tests/                  # pytest suite (95 tests)
doc/
  adr-001-architecture.md # Architecture decision record
  adr-002-quiz-engine.md  # Quiz data model and grading conventions
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

See [doc/DB-doc.md](doc/DB-doc.md) for the full schema — every column, the table relationships, and the delete-cascade behavior.

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

# Create and activate a virtual environment first
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies (using uv)
uv pip install -e ".[dev]"

# Or using pip
pip install -e ".[dev]"
```

### Running the app

**Native window (pywebview):**

```bash
python app.py
```

This starts the FastAPI server on `127.0.0.1:8764` and opens a native pywebview window.

On first run, the app creates a `data/app.db` SQLite database in the project root to hold your vocabulary, cards, and review history. The `data/` directory is created automatically and is gitignored — it is your personal data and never committed.

**Browser mode (recommended for development):**

```bash
python app.py --browser
```

This starts the server and opens `http://127.0.0.1:8764` in your default browser instead of pywebview. Useful for inspecting elements and debugging with browser DevTools.

You can also run both modes simultaneously — the server is accessible at `http://127.0.0.1:8764` in any browser while the native window is open.

### Running tests

```bash
pytest -q
```

There are currently 95 tests covering tokenization, dictionary lookup, furigana rendering, database operations, FSRS scheduling, quiz generation and grading, API endpoints, statistics, Anki export, and packaging.

### Linting

```bash
ruff check .
ruff format .
```

## Running with Docker

The desktop (pywebview) shell needs a GUI, so it cannot run inside a container. The image
instead runs the **FastAPI engine directly** and serves the same web UI on port `8764` —
equivalent to `python app.py --browser`. You open it in your own browser. Your vocabulary
database is persisted on the host through a volume, so it survives container rebuilds.

The dictionaries (SudachiDict, JMdict) are installed into the image at build time, so the
container needs no network access at runtime. The container publishes only to `127.0.0.1`,
keeping the "localhost only, never a public server" design decision intact.

### With Docker Compose (recommended)

```bash
# Build the image and start the container in the background
docker compose up -d --build

# Open the app in your browser
#   http://localhost:8764

# Follow logs / stop
docker compose logs -f
docker compose down
```

Your data lives in `./data/app.db` on the host (bind-mounted into the container) — the same
location used when running natively.

### With plain Docker

```bash
# Build the image
docker build -t japanese-reader .

# Run it — publishes to localhost only, persists the DB under ./data
docker run -d --name japanese-reader \
  -p 127.0.0.1:8764:8764 \
  -v "$(pwd)/data:/app/data" \
  japanese-reader

# Open http://localhost:8764 ; stop with:
docker rm -f japanese-reader
```

The first request after startup may take a moment while the dictionary loads.

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
| `GET` | `/quiz-page` | Quiz UI page |
| `GET` | `/quiz/next` | Generate a quiz question (`?type=reading\|meaning\|cloze\|mixed`) |
| `POST` | `/quiz/answer` | Submit a quiz answer and get the verdict + correct answer |
| `GET` | `/stats-page` | Statistics dashboard page |
| `GET` | `/stats` | Computed study statistics (accuracy, reviews/day) |
| `GET` | `/export/apkg` | Download vocabulary as Anki .apkg file |

## Building a standalone binary

The included `app.spec` bundles the web frontend, SudachiDict, and JMdict data into a single executable:

```bash
pyinstaller app.spec
```

The built binary will be in `dist/japanese-reader`. Resource paths are resolved at runtime via `server/resources.py`, which detects whether the app is running from source or from a PyInstaller bundle (`sys._MEIPASS`).
