# ADR-001: Architecture & Conventions

## Status
Accepted

## Context
We need fixed conventions before building the analysis engine, database, and UI so that every
later module agrees on data shapes, identity keys, and boundaries.

## Decisions

### Tokenizer: SudachiPy
SudachiPy (`sudachipy` + `sudachidict_core`) is the tokenizer. Confirmed in the Phase 0 spike:
- `m.surface()` — the word as written in the sentence (e.g. `食べ`)
- `m.dictionary_form()` — the lemma (e.g. `食べる`)
- `m.reading_form()` — katakana reading (e.g. `タベ`)
- `m.part_of_speech()` — tuple, first element is major class (e.g. `動詞`, `名詞`, `助詞`)

Split mode C (default) is used. A/B/C modes are available for learner-facing granularity later.

### Token contract
The single object that crosses from engine to UI:
```python
@dataclass
class Token:
    surface: str            # word as written
    reading_hiragana: str   # hiragana reading (converted from katakana)
    lemma: str              # dictionary form — the dedupe key
    meanings: list[str]     # English glosses from jamdict
    pos: tuple[str, ...]    # full POS tag tuple
    known: bool             # True if lemma is already in the user's vocab
```

### Dedupe key
`vocab.lemma` is `UNIQUE` in the database. The dictionary form is the canonical identity of a
word everywhere. `食べた`, `食べます`, `食べる` all resolve to the single lemma `食べる`.

### Reading normalization boundary
Katakana → hiragana conversion (`jaconv.kata2hira`) happens exactly once, inside `analyze()`.
Nothing downstream ever sees katakana readings.

### Engine/UI split
- Python engine behind a localhost-only FastAPI (`host="127.0.0.1"`).
- HTML/CSS/JS front end in a pywebview native window.
- The HTML boundary exists chiefly so furigana uses the native `<ruby>`/`<rt>` element.

### Furigana
Ship **naive whole-word** ruby first: `<ruby>surface<rt>reading</rt></ruby>`.
This is correct but not per-kanji pretty. Per-kanji alignment is a later polish task (Phase 6).

### Import order
Paste-text intake is the bulletproof baseline, built before any URL fetching or browser import.

### Dictionary: jamdict
`jamdict.Jamdict().lookup(lemma)` returns entries with senses containing English glosses.
On a miss, return an empty list — never raise.

### Spaced repetition: py-fsrs (MIT)
Use the `fsrs` package (`Scheduler`, `Card`, `Rating`). Never use Anki's AGPL source code.
Log every review from day one (`review_logs` table) for later FSRS parameter optimization.
