# ADR-002: Offline Quiz Engine — Data Model & Grading

## Status
Accepted

## Context
Before building the offline quiz engine (DEV-PLAN Part II — reading / meaning-recall / cloze
questions auto-generated from the user's vocabulary and imported texts), we need fixed conventions
so that Phases 1–5 become mechanical "fill in the function" work instead of re-litigating data
shapes mid-stream. These decisions cover the quiz data model, how the correct answer is represented
and graded, how the API remembers a question between requests, and where randomness lives.

The engine reuses existing infrastructure: SudachiPy (`server/analyze.py`), jamdict
(`server/dictionary.py` `lookup_meanings`), furigana rendering (`server/render.py` `render_ruby`),
and the FastAPI/web/test patterns already in the codebase. No new dependencies, no schema
migration, no network — consistent with the project's local-first principle.

## Decisions

### Pure logic / I-O split
All quiz *generation and grading* lives in `server/quiz.py` as **pure functions over plain
dataclasses** — no `sqlite3`, no `jamdict`, no HTTP. The API layer in `server/main.py` reads the
database and calls into `quiz.py`. This mirrors how `analyze.py` is pure and `main.py` wraps it,
and is what makes the logic unit-testable without a server.

### `VocabEntry` — the DB-free vocab unit
The pure layer operates on a plain row, decoupled from the SQLite schema (added in DEV-PLAN
Step 0.2):
```python
@dataclass(frozen=True)
class VocabEntry:
    lemma: str
    reading: str
    meaning: str
    pos: str
```
The API maps `vocab` rows to `VocabEntry` (meaning = `primary_meaning`) before calling generators.

### `Question` — one shape for all quiz types
```python
@dataclass(frozen=True)
class Question:
    kind: str                          # "reading" | "meaning" | "cloze"
    prompt: str                        # kanji word, word, or sentence with a blank
    choices: tuple[str, ...]           # the options shown to the user
    answer_index: int                  # index into choices of the correct one
    context_html: str | None = None    # furigana-rendered sentence (cloze only)
    target_lemma: str = ""             # the vocab word being tested
```
One shape across all three quiz types keeps the API and UI uniform.

### Choice count
1 correct + 3 distractors = **4 choices**, shuffled; `answer_index` records where the correct one
landed. Distractor selection (`pick_distractors`) excludes the target, prefers same-POS candidates,
and tops up from other POS when too few same-POS words exist.

### Grading is a pure function
```python
def grade(question: Question, choice_index: int) -> bool:
    return choice_index == question.answer_index
```
No I/O. An out-of-range index returns `False` (never raises). This is the single source of truth
for correctness, shared by the endpoint and any future FSRS-rating mapping.

### Cross-request state
`GET /quiz/next` mints a `question_id` (uuid4) and caches the generated `Question` in an
**in-process dict** (`_pending: dict[str, Question]`); `POST /quiz/answer` looks it up and grades.
Rationale: single-user localhost app, no need to persist; the `answer_index` is never sent to the
client, so the UI cannot trivially reveal it. **Tradeoff:** a server restart drops any in-flight
question — acceptable for this use case.

### RNG injection
Every function that makes a random choice takes an injected `rng: random.Random`. Tests pass
`random.Random(0)` for reproducible goldens; the endpoint constructs a fresh `random.Random()` per
request. The global `random` module is never called inside `quiz.py`.

### Scope
Offline only — quiz types A (reading / 漢字読み), B (meaning recall), C (cloze / 文脈規定).
Sense-structure (type E) and LLM-based disambiguation (type F) are out of scope here and tracked in
DEV-PLAN §3 Phases 2–3.
