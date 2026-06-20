# Japanese Reader + SRS — A Test-First ROADMAP

This roadmap builds a **local-first Japanese reading + spaced-repetition desktop app** in
Python, from the design sketched in [`DRAFT_PLAN.md`](DRAFT_PLAN.md). The end goal is the
workflow described there: **paste or fetch Japanese text, read it with furigana, click any word
to see its reading and meaning, auto-collect new vocabulary deduped against what you already
know, and review that vocabulary with the FSRS algorithm.** Every piece underneath — the
tokenizer wrapper, the dictionary lookup, the dedupe key, the importer tiers, the FSRS
scheduler persistence — is code *you* wrote and *you* tested.

The point is not just to get furigana on a screen. It is to build each language-processing
component against an oracle you *can* check — a known tokenization, a known dictionary meaning,
a known FSRS state transition, a database invariant — so that when something looks right on
screen, you actually know it *is* right, and when you change it later, a red test tells you the
moment you broke it.

It is written as a **test-driven (TDD) curriculum**. For every step you:

1. **Red** — write the test the step specifies, against a function/class that does not exist
   yet, and run it so you watch it **fail for the right reason** (`ImportError`, `AttributeError`,
   or a wrong value — not a typo in the test).
2. **Green** — write the smallest implementation that makes that test pass.
3. **(Refactor)** — clean it up while the test stays green.

You advance only when **both** are true: the test is *faithful* (it genuinely exercises the
behaviour — not a tautology you bent to make pass) **and** it is green.

---

## How we test: language oracles, anchored by data you can verify

Natural-language code feels untestable ("how do I assert a *translation*?"), but this domain is
friendlier than it looks: tokenizers, dictionaries, and schedulers are deterministic, and the
hard questions reduce to a handful of checkable oracle types. Every test below uses one of these.

| Oracle | What it proves | Example |
|---|---|---|
| **Golden / reference** | A known input produces a known output | `食べた` tokenizes to lemma `食べる`; jamdict lookup of `猫` contains the gloss `cat`; one FSRS `Good` review on a fresh card yields the exact stability the library returns |
| **Invariant / property** | A rule the system must always obey | `食べた`, `食べます`, `食べる` collapse to **one** `vocab` row (lemma dedupe); `kata2hira(kata2hira(x)) == kata2hira(x)` (idempotent); after any review the card's `due` is **strictly after** `last_review`; `analyze()` is pure — same text in, same tokens out |
| **Round-trip** | Encode-then-decode (or persist-then-load) recovers the original | a `Card` written to SQLite and read back equals the in-memory card field-for-field; `kata2hira` then a katakana re-render round-trips a pure-katakana word |
| **Contract / shape** | The data crossing a boundary has the promised structure | `/analyze` returns one token object per morpheme, each with `{surface, reading_hiragana, lemma, meanings, pos, known}`; "Keep" in triage creates **exactly one** card |
| **Behavioural** | A whole flow actually does its job | importing a real article yields a non-empty, deduped candidate list; reviewing a card repeatedly with `Good` pushes its `due` monotonically further out |

**Why we still test, even though the libraries "just work."** You are not testing SudachiPy or
py-fsrs — you trust those. You are testing *your wiring around them*: that you read the
**dictionary form** and not the surface, that you converted katakana to hiragana, that you keyed
dedupe on the lemma, that you persisted **every** FSRS field so a reloaded card schedules
identically. Those are exactly the seams where a "looks fine on screen" app silently rots.

---

## The faithfulness check (read this twice)

A test that asserts nothing, asserts something always-true, or that you edited to stop failing,
is **not** a pass — it is a silent hole. Before you trust a green bar, **sabotage your own
implementation** (return the surface instead of the lemma, skip the kana conversion, key dedupe
on the wrong column) and confirm the test goes red. Every step below names the specific sabotage
to try. If breaking the behaviour does *not* turn the bar red, your test isn't testing — fix
that before moving on.

---

## How to read each step

Every step has the same shape. Read it top to bottom: the prose orients you first, the specifics
then pin down the exact behaviour, and finally the test / implementation / gate turn it green.
The single most important part is **"What we're building"** — read it before the specifics,
because the details only make sense once you know what they're *for*.

> **Goal** — the one-sentence outcome.
>
> **What we're building (read this first)** — a plain-English orientation: what the component
> *is*, the job it does inside the app, and a walk through each moving part — *before* any API
> detail. This is the part that makes the step understandable; everything below is detail hung on
> this frame.
>
> **Specifics** — the exact behaviour, fields, and library calls your test must assert, so you
> pin down the *true* answer rather than a guess.
>
> **Red — write the test** — the test file, the interface it pins down, the oracle type, the
> assertions, and a **worked example** (tiny concrete input and the value you expect back). End
> of Red = a test that **fails for the right reason** (usually the thing under test doesn't exist
> yet, so the import fails).
>
> **Green — make it pass** — the implementation to write, plus the one subtlety most likely to
> bite.
>
> **Why it matters** — the transferable skill or the bug this prevents.
>
> **Gate** — the command that must pass, plus the **faithfulness sabotage**: a change you make to
> your own code to confirm the test goes red.
>
> **Commit** — a [Conventional Commits](https://www.conventionalcommits.org/) message. One green
> gate = one commit.

---

## Conventions for this codebase (fix them once, use everywhere)

- **Python 3.11+**, full **type hints**, `snake_case` functions, `PascalCase` classes,
  `@dataclass` (or Pydantic models on the API boundary) for structured records.
- **Tests with `pytest`**, one test module per source module: `server/analyze.py` ↔
  `tests/test_analyze.py`. Run everything with `pytest -q` from the project root.
- **Lint/format** with `ruff` (`ruff check .` and `ruff format .`); keep the tree clean before
  each commit.
- **Store the dictionary form (lemma), never the surface form** — this is *the* invariant that
  makes "don't re-collect words I have" work. `食べた`/`食べます`/`食べる` must all map to the lemma
  `食べる`. (Gotcha #1 in the draft plan.)
- **Convert Sudachi's katakana readings to hiragana** with `jaconv.kata2hira(...)` at the one
  boundary where readings enter the system, so nothing downstream ever sees katakana. (Gotcha #2.)
- **Bind FastAPI to `127.0.0.1` only.** It is a local app, never a public server. (Gotcha #4.)
- **Create `review_logs` from day one** (Phase 5), even before anything reads them — you need the
  history to optimize FSRS later. (Gotcha #5.)
- **Determinism in tests.** Tokenizer and dictionary objects are expensive to build and
  deterministic to call — load them **once** in a session-scoped fixture. Anything time-dependent
  (FSRS `due` dates, `created_at`) takes an **injected clock / `now`** argument so tests pass a
  fixed timestamp instead of `datetime.now()`.
- **Tests own their database.** Every DB test runs against a fresh schema in a `tmp_path` SQLite
  file (or `:memory:`), created by a fixture — never the app's real `data/` database.

---

## Wiring: the test harness you build once (Phase 0) and reuse everywhere

Unlike a compiled project there is no build graph to maintain, but there *are* three fixtures
that every later phase leans on. Stand them up in `tests/conftest.py` during Phase 0 so each
later step is "write the test, write the code" with no setup friction:

- **`tokenizer`** *(session-scoped)* — a single `sudachipy.Dictionary().create()` tokenizer,
  built once and shared. SudachiDict loads slowly; rebuilding it per-test makes the suite crawl.
- **`dictionary`** *(session-scoped)* — a single `jamdict.Jamdict()` instance, shared the same way.
- **`db`** *(function-scoped)* — a fresh SQLite connection with the full schema applied, on a
  `tmp_path` file, torn down after each test. This is what keeps DB tests isolated and repeatable.

The FastAPI tests (Phase 2+) use Starlette's `TestClient(app)` with the `db` fixture injected via
dependency override, so endpoint tests hit a throwaway database, never `data/app.db`.

After any change, re-run the whole suite from the project root and confirm your **new test name**
appears and passes — don't trust a green bar that only ran the old tests:

```
pytest -q
```

---

## Architecture & data model (recap — full detail in DRAFT_PLAN.md §3–§4)

Local client-server. A Python "engine" (all language logic + the database) sits behind a
localhost-only FastAPI, with an HTML/CSS/JS front end shown in a native window via **pywebview**.
The HTML boundary exists chiefly so furigana can use HTML's native `<ruby>`/`<rt>`. Project
layout, the SQLite schema (`texts`, `vocab`, `cards`, `review_logs`), and the tech-stack table
live in [`DRAFT_PLAN.md`](DRAFT_PLAN.md) — this roadmap turns that design into ordered,
test-first steps. The single most important schema fact: **`vocab.lemma` is `UNIQUE`**, and
scheduling state (`cards`) is kept in a separate table from linguistic content (`vocab`).

**Build order rationale:** riskiest unknowns first. Phase 0 proves the two libraries you don't
control (tokenizer, dictionary) actually do what you need on messy real text *before* you build
anything on top of them. Each phase after that ends with something usable.

---

## Phase 0 — Foundations & spike: de-risk the unknowns

This phase writes almost no product code. It proves the unpredictable third-party pieces work on
real Japanese, stands up the test harness, and records the decisions everything else assumes.

### Step 0.1 — Green pytest pipeline + project skeleton

**Goal:** `pytest -q` runs and passes a trivial test, so every later Red/Green is measured
against a known-good, trustworthy baseline.

**What we're building (read this first).** Before any language code, you need one command that
discovers and runs every test and comes back **green**. This is not busywork: TDD only works if
"all green" is a state you can trust and return to. If your runner is silently finding *zero*
tests, then later, when a real test passes, you won't know whether the code is right or the
runner just isn't running it. So: create the package skeleton (`server/`, `web/`, `tests/`,
`pyproject.toml`), install the core dependencies, and prove the harness is honest with one
sentinel test.

**Specifics:** create `pyproject.toml` declaring the core deps (`sudachipy`, `sudachidict_core`,
`jamdict`, `jamdict-data`, `jaconv`, `fsrs`, `trafilatura`, `fastapi`, `uvicorn`, `pywebview`)
and dev deps (`pytest`, `ruff`). Lay out `server/`, `web/`, `data/`, `tests/` per DRAFT_PLAN §3.

**Red — write the test:** `tests/test_smoke.py` with `def test_harness_runs(): assert True`. Run
`pytest -q`. The "red" here is the *failure mode to rule out*: if pytest prints
`collected 0 items`, your layout or config is wrong — fix it until pytest finds and runs the
sentinel.

**Green — make it pass:** get `pytest -q` to collect and pass exactly one test; confirm
`ruff check .` is clean.

**Why it matters:** A runner that finds no tests but exits 0 is worse than a failing one — it
lies. Establish a baseline you can trust before you build on it.

**Gate:** `pytest -q` names and passes `test_harness_runs`. **Faithfulness:** flip the sentinel
to `assert False` → the bar goes red → revert. (If it stays green, pytest isn't running your
file.)

**Commit:** `chore: scaffold project and green pytest harness`

### Step 0.2 — Tokenizer spike + decision gate (SudachiPy vs fugashi)

**Goal:** Prove the tokenizer turns real, messy Japanese into the three fields the whole app
depends on — **surface, dictionary form, reading** — and decide SudachiPy vs fugashi here, once.

**What we're building (read this first).** The tokenizer is the riskiest dependency: everything
downstream (furigana, dedupe, vocab, cards) is built on its output, so you prove it *first*, in
isolation, on a real sentence — not a toy. The one subtlety that bites everyone: a token's
**surface** is the word as written in this sentence (`食べた`), but its **dictionary form** is the
lemma you must store and look up (`食べる`). Sudachi exposes them as separate methods, and confusing
them silently breaks dedupe two phases from now. You also confirm the reading comes back as
**katakana** (`タベ`), which is why Step 1.2 exists.

**Specifics:** with a tokenizer from `sudachipy.Dictionary().create()`, for each morpheme `m`:
`m.surface()`, `m.dictionary_form()` (the lemma), `m.reading_form()` (katakana), and
`m.part_of_speech()` — a list whose **first element** is the major class (`動詞` verb, `名詞` noun,
`助詞` particle, …). Use split mode C for the spike.

**Red — write the test:** `tests/test_spike_tokenizer.py`:
- `test_dictionary_form_differs_from_surface` *(golden)*: **worked example** — tokenizing
  `今日は寿司を食べた` ("today I ate sushi"), the morpheme with surface `食べた` has
  `dictionary_form() == "食べる"` and `reading_form() == "タベ"` (katakana, *not* hiragana).
- `test_pos_identifies_particle` *(golden)*: the `を` morpheme has `part_of_speech()[0] == "助詞"`.
- Run → **red** until you write the thin spike helper.

**Green — make it pass:** a throwaway `spike/tokenize.py` that builds the tokenizer and returns
`(surface, dictionary_form, reading_form, pos)` tuples. Run it on a few real sentences and eyeball
the output. **Decision gate:** if SudachiPy installs and reads cleanly, adopt it (its A/B/C split
modes help learners later); if its dictionary install is painful on your platform, switch to
`fugashi` + `unidic-lite` now — the field names differ but the three-field contract is the same.
Record the choice in the ADR (Step 0.4).

**Why it matters:** This is the project's single biggest unknown. Proving the surface≠lemma
distinction *now*, on real text, is what stops a silent dedupe bug in Phase 4.

**Gate:** both spike tests pass. **Faithfulness:** assert `dictionary_form() == "食べた"` (the
surface) → the test goes red, proving it really distinguishes lemma from surface.

**Commit:** `spike: verify tokenizer surface/lemma/reading on real text`

### Step 0.3 — Dictionary spike (jamdict lemma → meanings)

**Goal:** Prove jamdict returns usable English meanings for the **dictionary form**, end to end
with the tokenizer.

**What we're building (read this first).** The other dependency you don't control is the
dictionary. You prove that the lemma the tokenizer hands you (`食べる`, not `食べた`) actually finds
entries in jamdict and yields English glosses. This closes the spike loop: *raw sentence →
morphemes → lemma → meanings*. If this works on messy real text, the project is de-risked and
Phase 1 is just "wrap the spike cleanly."

**Specifics:** `jamdict.Jamdict().lookup(lemma)` returns a result whose `.entries` each carry
`senses`, each with `gloss` texts. Extract the gloss strings. Looking up the **lemma** matters:
`食べる` resolves; the inflected surface `食べた` may not.

**Red — write the test:** `tests/test_spike_dictionary.py`:
- `test_lookup_returns_english_gloss` *(golden)*: **worked example** — `lookup("猫")` yields glosses
  containing `"cat"`; `lookup("食べる")` yields glosses containing `"eat"`.
- `test_lemma_lookup_beats_surface` *(invariant)*: looking up the lemma `食べる` returns at least one
  entry (the property the app relies on — store/look up lemmas, not surfaces).
- Run → **red**.

**Green — make it pass:** a `spike/lookup.py` that maps a lemma to a list of gloss strings. Run
the *combined* spike (tokenize a sentence → look up each lemma) and confirm it works on a real,
messy paragraph. **This is the "project de-risked" checkpoint.**

**Why it matters:** Confirms the two libraries compose on real input — the whole reader rests on
this lemma→meaning path.

**Gate:** both dictionary spike tests pass. **Faithfulness:** look up `m.surface()` instead of the
lemma for an inflected verb → the gloss list comes back empty/wrong → red.

**Commit:** `spike: verify jamdict lemma lookup composes with tokenizer`

### Step 0.4 — Architecture decision record (design checkpoint)

**Goal:** Decide, once and in writing, the conventions Phases 1–6 assume, so each later step is
mechanical "fill in the function" work instead of re-litigating the same questions mid-stream.

**What we're building (read this first).** This step produces a *document*, not code. An **ADR**
records one set of design decisions — context, choice, reasoning — so weeks later nobody
(including you) reverse-engineers "why is it built this way?". You fix the handful of conventions
every module leans on.

**Decisions to record (in `doc/adr-001-architecture.md`):**
- **Tokenizer:** SudachiPy (or fugashi) — whichever the Step 0.2 gate chose, and why.
- **The `Token` contract:** `{surface, reading_hiragana, lemma, meanings: list[str], pos, known:
  bool}` — the single object that crosses from engine to UI (DRAFT_PLAN §5).
- **Dedupe key:** `vocab.lemma` is `UNIQUE`; the dictionary form is the canonical identity of a
  word everywhere.
- **Reading normalization boundary:** katakana→hiragana happens exactly once, inside `analyze()`;
  nothing downstream sees katakana.
- **Engine/UI split:** Python engine behind a localhost FastAPI; HTML/JS front end (chiefly so
  `<ruby>` furigana is native). Bind `127.0.0.1`.
- **Furigana:** ship **naive whole-word** ruby first (correct, just not per-kanji pretty);
  per-kanji alignment is a later, self-contained polish task (DRAFT_PLAN §5, Phase 6).
- **Scope/order:** paste-text intake is the bulletproof baseline built before any fetching.

**Checkpoint (not a unit test):** the ADR exists and the `Token` contract is concrete enough to
paste straight into Step 1.4's test.

**Why it matters:** One good decision recorded here turns Phases 1–6 into a sequence of small
unambiguous wins instead of a running argument with yourself.

**Gate:** ADR written; the `Token` contract is concrete enough to copy into a later test.

**Commit:** `docs(adr): record token contract, dedupe key, and engine/UI split`

---

## Phase 1 — Analysis engine (the heart of the reader)

Pure functions that turn raw Japanese into annotated tokens. No UI, no database yet — just the
language pipeline, fully tested, because everything else consumes it.

### Step 1.1 — `Token` dataclass + `tokenize()` wrapper

**Goal:** Wrap the spike's tokenizer call in a typed `tokenize(text) -> list[RawToken]` that
exposes surface, lemma, katakana reading, and POS.

**What we're building (read this first).** You promote the throwaway spike into a real,
tested function. `tokenize()` runs the shared tokenizer over a string and returns one structured
record per morpheme — still with the **katakana** reading (hiragana conversion is the next step)
and the **full POS tuple** (the filter that needs it comes in Phase 4). Keeping this layer thin
and typed means every later step talks to *your* stable record, not Sudachi's raw object.

**Specifics:** `RawToken` = `{surface, lemma, reading_katakana, pos: tuple[str, ...]}`. Use the
`tokenizer` fixture (Step 0 wiring). `lemma = m.dictionary_form()`, `reading_katakana =
m.reading_form()`, `pos = tuple(m.part_of_speech())`.

**Red — write the test:** `tests/test_analyze.py`:
- `test_tokenize_lemma_and_reading` *(golden)*: **worked example** — `tokenize("本を読む")` contains a
  token with `lemma == "読む"` and `reading_katakana == "ヨ" `-prefixed reading for the verb stem;
  the `本` token has `lemma == "本"`.
- `test_tokenize_is_pure` *(invariant)*: calling `tokenize(s)` twice returns equal results.
- Run → **red** (`tokenize` doesn't exist).

**Green — make it pass:** write `server/analyze.py::tokenize` and the `RawToken` dataclass.

**Why it matters:** A thin, typed boundary over the tokenizer is what lets every later step depend
on a stable shape instead of the library's internals.

**Gate:** the tokenize tests pass. **Faithfulness:** set `lemma = m.surface()` →
`test_tokenize_lemma_and_reading` goes red for the inflected verb.

**Commit:** `feat(analyze): typed tokenize() wrapper over the tokenizer`

### Step 1.2 — Katakana → hiragana reading conversion

**Goal:** Convert Sudachi's katakana readings to hiragana, at one boundary, so furigana shows
`たべる` not `タベル`.

**What we're building (read this first).** Sudachi gives readings in **katakana**; learners expect
furigana in **hiragana**. `jaconv.kata2hira` does the conversion, and the design rule is to do it
in exactly one place so nothing downstream ever has to think about it. The property worth pinning:
conversion is **idempotent** — converting an already-hiragana string leaves it unchanged — so it's
safe even on mixed input.

**Specifics:** `to_hiragana(reading_katakana) -> str` wraps `jaconv.kata2hira`. `タベル → たべる`;
`ねこ → ねこ` (unchanged); `kata2hira` is idempotent.

**Red — write the test:** in `tests/test_analyze.py`:
- `test_kata_to_hira` *(golden)*: **worked example** — `to_hiragana("タベル") == "たべる"`.
- `test_kata_to_hira_idempotent` *(invariant)*: `to_hiragana(to_hiragana(x)) == to_hiragana(x)` for
  `x in {"タベル", "ねこ"}`.
- Run → **red**.

**Green — make it pass:** write `server/analyze.py::to_hiragana`.

**Why it matters:** Doing the conversion at a single boundary (and proving idempotence) is what
keeps katakana from leaking into the UI or the database.

**Gate:** the conversion tests pass. **Faithfulness:** make `to_hiragana` return its input
unchanged → `test_kata_to_hira` goes red.

**Commit:** `feat(analyze): katakana→hiragana reading conversion`

### Step 1.3 — Dictionary lookup (lemma → meanings)

**Goal:** `lookup_meanings(lemma) -> list[str]` returning English glosses, with a clean empty
result for words not in the dictionary.

**What we're building (read this first).** This promotes the dictionary spike into a tested
function and decides the one policy that matters: **what happens when a lemma isn't found?** Proper
nouns, slang, and rare compounds won't be in JMdict, and the reader must degrade gracefully —
return an empty list, never raise — so an unknown word still renders (just without a gloss).

**Specifics:** `lookup_meanings(lemma)` queries the shared `dictionary` fixture, flattens
`entries → senses → glosses` to a `list[str]`, and returns `[]` for a miss. Optionally cap the
number of glosses for UI sanity.

**Red — write the test:** in `tests/test_dictionary.py`:
- `test_known_word_has_meaning` *(golden)*: `"猫"` → glosses contain `"cat"`.
- `test_unknown_word_returns_empty` *(contract)*: a clearly-absent string (e.g. a nonsense kana run
  `"ぬるぽぽぽ"`) returns `[]` and does **not** raise.
- Run → **red**.

**Green — make it pass:** write `server/dictionary.py::lookup_meanings`.

**Why it matters:** Real text is full of out-of-dictionary words; a lookup that raises on a miss
would break the reader on the first proper noun.

**Gate:** the lookup tests pass. **Faithfulness:** let a miss raise instead of returning `[]` →
`test_unknown_word_returns_empty` goes red.

**Commit:** `feat(dictionary): lemma→meanings lookup with graceful miss`

### Step 1.4 — `analyze(text) -> list[Token]` (assemble the pipeline)

**Goal:** Compose tokenize → hiragana → lookup into the single display `Token` the UI consumes.

**What we're building (read this first).** This is the heart of the reader: the one function the
front end calls. For each morpheme it assembles the full display `Token` from the ADR —
`{surface, reading_hiragana, lemma, meanings, pos, known}` — by running the three pieces you just
built in sequence. `known` is left `False` here (it depends on the database, wired in Phase 3);
pinning it `False` now keeps the analysis engine free of storage concerns.

**Specifics:** `analyze(text) -> list[Token]`: for each `RawToken`, set `reading_hiragana =
to_hiragana(reading_katakana)`, `meanings = lookup_meanings(lemma)`, `known = False`. The `Token`
fields match the ADR contract exactly.

**Red — write the test:** in `tests/test_analyze.py`:
- `test_analyze_full_token` *(contract + golden)*: **worked example** — `analyze("猫を見た")` returns
  tokens; the `見た` token has `lemma == "見る"`, `reading_hiragana == "みた"`-consistent hiragana (no
  katakana), and `"cat"` appears in the `猫` token's `meanings`.
- `test_analyze_emits_all_fields` *(contract)*: every token has all six fields populated and
  `known is False`.
- Run → **red**.

**Green — make it pass:** write `server/analyze.py::analyze` composing the three functions.

**Why it matters:** This is the function the entire UI is built on; getting its contract exact and
tested means the front end can trust every field.

**Gate:** the analyze tests pass. **Faithfulness:** skip `to_hiragana` (pass the katakana reading
straight through) → `test_analyze_full_token`'s "no katakana" assertion goes red.

**Commit:** `feat(analyze): assemble analyze(text) -> list[Token]`

### Step 1.5 — Analysis caching

**Goal:** Cache `analyze()` results per text so reopening a text doesn't re-tokenize.

**What we're building (read this first).** Tokenizing + looking up a long article is not free, and
the reader will re-open the same text often. You add a cache keyed on the text content, and prove
the property that makes a cache *correct*: a cached result must be **identical** to a fresh
analysis, never stale or different. (For now an in-process LRU is enough; Phase 3 persists the
analysis JSON in the `texts` table.)

**Specifics:** wrap `analyze` so a repeat call with the same text returns an equal result without
re-running the tokenizer. Verify cache *correctness* (cached == fresh), and optionally that the
tokenizer was invoked once (via a spy/mock).

**Red — write the test:** in `tests/test_analyze.py`:
- `test_cache_returns_equal_result` *(invariant)*: `analyze_cached(s) == analyze(s)`.
- `test_cache_hits_skip_tokenizer` *(behavioural)*: with the tokenizer call counted, a second
  `analyze_cached(s)` does not increment the count.
- Run → **red**.

**Green — make it pass:** add `functools.lru_cache` (or an explicit dict keyed by text hash) around
the pipeline.

**Why it matters:** A cache that can return a *different* answer than a fresh run is a bug
generator; the equality test is what keeps it honest.

**Gate:** the cache tests pass. **Faithfulness:** make the cache return a hard-coded `[]` on hits →
`test_cache_returns_equal_result` goes red.

**Commit:** `feat(analyze): cache analysis results per text`

---

## Phase 2 — Reader UI: paste, read with furigana, tap to translate

Expose the engine over a localhost API and render it. **Deliverable:** paste an article, read it
with furigana, click a word for its reading and meaning. Already useful.

### Step 2.1 — FastAPI `/analyze` endpoint (localhost-only)

**Goal:** A `POST /analyze` that takes text and returns the token list as JSON, bound to
`127.0.0.1`.

**What we're building (read this first).** The front end is HTML/JS, so the engine needs an HTTP
door. You add one endpoint that accepts `{text}` and returns the `analyze()` token list as JSON.
The security rule from the gotchas is non-negotiable and *testable*: the server binds
`127.0.0.1` only — it's a personal app, not a public service.

**Specifics:** `POST /analyze` with body `{text: str}` → `{tokens: [Token, …]}`. Use Pydantic
models for request/response. Test with `TestClient(app)`. The uvicorn launcher (Step 2.3) passes
`host="127.0.0.1"`.

**Red — write the test:** `tests/test_api.py`:
- `test_analyze_endpoint_shape` *(contract)*: **worked example** — `POST /analyze {"text": "猫を見た"}`
  returns 200 and a `tokens` array whose first element has the six `Token` fields.
- `test_analyze_endpoint_empty_text` *(edge)*: empty text returns 200 with an empty `tokens` list
  (not a 500).
- Run → **red**.

**Green — make it pass:** write `server/main.py` with the FastAPI app and the route; add a startup
assertion or config pinning the host to `127.0.0.1`.

**Why it matters:** This is the engine/UI boundary; locking it to localhost and pinning its JSON
shape are what make the front end both safe and simple.

**Gate:** the endpoint tests pass. **Faithfulness:** return the raw `RawToken`s (missing
`reading_hiragana`/`meanings`) → `test_analyze_endpoint_shape` goes red on the field check.

**Commit:** `feat(api): POST /analyze endpoint (localhost-only)`

### Step 2.2 — Furigana rendering (naive whole-word `<ruby>`)

**Goal:** Turn a `Token` into `<ruby>surface<rt>reading</rt></ruby>`, correctly escaped, with no
ruby for kana-only words.

**What we're building (read this first).** Furigana is the feature HTML makes easy: a `<ruby>`
element puts the reading (`<rt>`) above the base text. Per the ADR you ship the **naive
whole-word** version first — the whole reading over the whole word — which is *correct*, just not
per-kanji pretty (`食べる` shows `食べる(たべる)`). Two rules keep it sane: don't add ruby to a word
that's already all kana (`ねこ` needs none), and **HTML-escape** the surface so text like `<` or `&`
can't break the page. Per-kanji alignment is explicitly deferred to Phase 6.

**Specifics:** `render_ruby(token) -> str`. If the surface contains no kanji, return the escaped
surface unchanged. Otherwise return `<ruby>{escaped_surface}<rt>{reading_hiragana}</rt></ruby>`.
Use `html.escape`.

**Red — write the test:** `tests/test_render.py`:
- `test_ruby_for_kanji_word` *(golden)*: **worked example** — a token `{surface:"猫",
  reading_hiragana:"ねこ"}` renders to `<ruby>猫<rt>ねこ</rt></ruby>`.
- `test_no_ruby_for_kana` *(invariant)*: a kana-only surface `ねこ` renders to just `ねこ` (no `<ruby>`).
- `test_surface_is_escaped` *(security)*: a surface containing `<` is HTML-escaped in the output.
- Run → **red**.

**Green — make it pass:** write `server/render.py::render_ruby` (a kanji-detection helper over the
CJK Unified Ideographs range).

**Why it matters:** This is the reader's signature feature; shipping the correct naive version now
(and not blocking on per-kanji alignment) is exactly the draft plan's advice.

**Gate:** the render tests pass. **Faithfulness:** drop `html.escape` →
`test_surface_is_escaped` goes red.

**Commit:** `feat(render): naive whole-word furigana ruby`

### Step 2.3 — pywebview shell + reader page

**Goal:** A double-click launcher that starts FastAPI on `127.0.0.1` and opens a native window
showing the reader.

**What we're building (read this first).** This assembles the app you actually *run*: `app.py`
starts uvicorn on a localhost port in a background thread, then opens a pywebview window pointed at
it. The reader page has a textarea, an "Analyze" button, and a render area that calls `/analyze`
and draws the ruby HTML. Most of this is glue and eyeballing, so the *automated* test targets the
one piece that can silently break: the launcher must actually bring the server up and serve the
page.

**Specifics:** `app.py` runs uvicorn (`host="127.0.0.1"`, an ephemeral or fixed port) on a thread,
waits for readiness, then `webview.create_window(...)`. `web/index.html` + `web/reader.js` fetch
`/analyze` and inject `render_ruby` output.

**Red — write the test:** `tests/test_app_launch.py`:
- `test_server_serves_reader` *(smoke)*: start the server helper (not the GUI), `GET /` returns 200
  and HTML containing the reader's textarea id. (Factor server-start out of `app.py` so it runs
  headlessly, exactly as the PID roadmap factors `runDemo()` from plotting.)
- Run → **red**.

**Green — make it pass:** implement the server-start helper and a `GET /` that serves
`web/index.html`; have `app.py` call the helper then open the window.

**Why it matters:** Keeping launch logic testable (separate from the GUI window) means the app
can't silently fail to start between changes.

**Gate:** `test_server_serves_reader` passes; manually, `python app.py` opens a window where pasted
text renders with furigana. **Faithfulness:** point `GET /` at a missing file → the smoke test goes
red.

**Commit:** `feat(app): pywebview shell serving the reader`

### Step 2.4 — Word popover (reading + meanings)

**Goal:** Clicking a word shows a popover with its reading and English meanings.

**What we're building (read this first).** The reader's second core interaction: tap a word, see
what it means. The data is already in each `Token` (`reading_hiragana`, `meanings`) — this step is
mostly front-end wiring to attach each rendered word to its token and show a popover on click. To
keep it testable, the click handler reads from a per-word `data-` payload the server emits, so the
*contract* of that payload is what you assert.

**Specifics:** each rendered word carries its `lemma`, `reading_hiragana`, and `meanings` (e.g. as
`data-` attributes or a parallel JSON array the JS indexes). The popover shows reading + up to N
meanings; words with empty `meanings` show "(no dictionary entry)".

**Red — write the test:** `tests/test_render.py`:
- `test_word_payload_carries_meanings` *(contract)*: the render function for a clickable word
  includes the token's `lemma` and at least one meaning in its emitted payload for `猫`.
- `test_empty_meanings_payload` *(edge)*: a word with `meanings == []` still emits a well-formed
  payload (empty meanings array), so the JS can show the fallback.
- Run → **red**.

**Green — make it pass:** extend the renderer to emit per-word payloads; add `web/reader.js` popover
logic and `web/style.css`.

**Why it matters:** Tap-to-translate is the reason to use the app over a plain text file; pinning
the payload contract keeps the JS honest without a browser in the loop.

**Gate:** the payload tests pass; manually, clicking a word shows its reading + meanings.
**Faithfulness:** omit `meanings` from the payload → `test_word_payload_carries_meanings` goes red.

**Commit:** `feat(reader): click-word popover with reading and meanings`

---

## Phase 3 — Vocabulary storage: a deduped personal word list

Add SQLite and the `texts`/`vocab` tables. **Deliverable:** a growing word list, deduped by lemma,
with already-saved words marked in the reader.

### Step 3.1 — SQLite schema + `db` module

**Goal:** Create the `texts` and `vocab` tables and a `db` module that applies the schema to a
connection.

**What we're building (read this first).** This is the persistence foundation. You write the
schema from DRAFT_PLAN §4 — crucially with `vocab.lemma` declared **`UNIQUE`**, the constraint
that *enforces* dedupe at the database level — and a small module that opens a connection and
applies the schema. The test proves the schema loads and the uniqueness constraint is really
there (not just intended).

**Specifics:** `db.connect(path) -> Connection` applies `texts` and `vocab` per DRAFT_PLAN §4.
`vocab.lemma TEXT NOT NULL UNIQUE`. Timestamps as ISO-8601 TEXT. The `db` fixture (Step 0 wiring)
returns a connection on a `tmp_path` file.

**Red — write the test:** `tests/test_db.py`:
- `test_schema_creates_tables` *(contract)*: after `connect`, `texts` and `vocab` exist with the
  expected columns.
- `test_lemma_unique_constraint` *(invariant)*: inserting two rows with the same `lemma` raises an
  `IntegrityError`.
- Run → **red**.

**Green — make it pass:** write `server/db.py` with the `CREATE TABLE` statements and `connect`.

**Why it matters:** The `UNIQUE` constraint is the database-level guarantee behind "don't
re-collect words I have"; proving it now means later dedupe code can rely on it.

**Gate:** the schema tests pass. **Faithfulness:** drop `UNIQUE` from `lemma` →
`test_lemma_unique_constraint` goes red.

**Commit:** `feat(db): texts + vocab schema with unique lemma`

### Step 3.2 — Vocab upsert deduped by lemma

**Goal:** `upsert_vocab(lemma, …)` that inserts a new word or, if the lemma exists, bumps its
counts instead of duplicating it.

**What we're building (read this first).** This is where the app's promise — *don't show me words I
already have* — becomes real code. `upsert_vocab` either creates a `vocab` row for a new lemma or,
for one already present, increments its `seen_count` (and `text_count` when seen in a new text)
rather than inserting a duplicate. The headline invariant: feeding in `食べた`, then `食べます`, then
`食べる` — three surfaces of one verb — must leave **exactly one** row, with `seen_count == 3`.

**Specifics:** `upsert_vocab(conn, lemma, reading, meaning, pos, text_id)`: `INSERT … ON CONFLICT
(lemma) DO UPDATE SET seen_count = seen_count + 1` (and increment `text_count` when this `text_id`
is new for the lemma). Returns the `vocab.id`.

**Red — write the test:** `tests/test_db.py`:
- `test_inflections_dedupe_to_one_row` *(invariant — the crux)*: **worked example** — upsert the
  lemma `食べる` three times (as it would arrive from `食べた`/`食べます`/`食べる`); `vocab` has one row
  with `seen_count == 3`.
- `test_distinct_lemmas_create_distinct_rows` *(contract)*: upserting `猫` and `犬` yields two rows.
- Run → **red**.

**Green — make it pass:** write `server/db.py::upsert_vocab` with the `ON CONFLICT` upsert.

**Why it matters:** This is *the* feature that keeps the word list from drowning you in
re-collected words; the inflection test is its definition.

**Gate:** the dedupe tests pass. **Faithfulness:** change the conflict target to the `id` (or use a
plain `INSERT`) → `test_inflections_dedupe_to_one_row` produces three rows → red.

**Commit:** `feat(db): upsert_vocab deduped by lemma with counts`

### Step 3.3 — "Save word" endpoint + popover button

**Goal:** A `POST /vocab` that saves a clicked word, wired to a "Save" button on the popover.

**What we're building (read this first).** Now the reader can *grow* your word list. The popover
gets a "Save" button that posts the clicked word's lemma/reading/meaning to a new endpoint, which
calls `upsert_vocab`. Because saving is idempotent at the lemma level (Step 3.2), saving the same
word twice is harmless — and that's worth asserting so the UI never needs to guard against
double-clicks.

**Specifics:** `POST /vocab {lemma, reading, meaning, pos, text_id?}` → `{id, created: bool}`.
Internally calls `upsert_vocab`. `GET /vocab` lists saved words (for Step 3.4).

**Red — write the test:** `tests/test_api.py`:
- `test_save_word` *(contract)*: `POST /vocab` for `猫` returns 200 with an `id`; `GET /vocab` then
  includes `猫`.
- `test_save_word_twice_is_idempotent` *(invariant)*: posting `猫` twice leaves a single vocab row.
- Run → **red**.

**Green — make it pass:** add the routes to `server/main.py`; add the Save button + fetch call to
`web/reader.js`.

**Why it matters:** Turns passive reading into an active, growing personal lexicon — the bridge to
the SRS.

**Gate:** the save tests pass; manually, the Save button adds a word. **Faithfulness:** swap the
endpoint to a plain `INSERT` → `test_save_word_twice_is_idempotent` goes red.

**Commit:** `feat(api): save-word endpoint and popover button`

### Step 3.4 — Vocab list screen + known-word styling in the reader

**Goal:** A vocab-list view with search/filter, and reader words styled by whether they're already
saved.

**What we're building (read this first).** Two payoffs of having a word list. First, a screen that
lists your saved vocab with search/filter so you can browse what you've collected. Second — and
this is where `Token.known` finally gets used — the reader marks words you already know, so your
eye is drawn to the genuinely new ones. To do that, `analyze()` gains an optional "known lemmas"
lookup against the DB, setting `known=True` for saved words; the invariant is that a word's `known`
flag matches its presence in `vocab`.

**Specifics:** `analyze(text, known_lemmas: set[str] | None)` sets `known = lemma in known_lemmas`.
`GET /vocab?q=…` filters by substring. Reader applies a CSS class to `known` words.

**Red — write the test:** `tests/test_analyze.py` and `tests/test_api.py`:
- `test_known_flag_set_from_vocab` *(invariant)*: with `known_lemmas={"猫"}`, `analyze("猫を見た")` marks
  the `猫` token `known=True` and the `見る` token `known=False`.
- `test_vocab_search_filters` *(contract)*: with `猫` and `犬` saved, `GET /vocab?q=猫` returns only `猫`.
- Run → **red**.

**Green — make it pass:** thread `known_lemmas` through `analyze`; add the filtered list route and
`web/` vocab screen + CSS.

**Why it matters:** "Known" styling is what makes re-reading efficient — your attention goes to new
words, which is the entire learning loop.

**Gate:** the known-flag and search tests pass. **Faithfulness:** hard-code `known=False` in
`analyze` → `test_known_flag_set_from_vocab` goes red.

**Commit:** `feat(vocab): vocab list, search, and known-word styling`

---

## Phase 4 — Import + auto-vocab (the feature you asked for)

Turn an article into a triaged list of genuinely-new words. Build source-agnostic logic first
(works on pasted text), then add fetch tiers. **Deliverable:** import news/stories from text,
friendly URLs, or the in-app browser, and auto-build triaged vocab.

### Step 4.1 — Tier-1 paste intake

**Goal:** Accept pasted article text, persist it as a `texts` row, and return its analysis.

**What we're building (read this first).** Per the draft plan, **paste is the bulletproof
baseline** — it works for *any* source, including bot-blocked sites, so it's built before any
fetching exists. This endpoint takes raw pasted text, stores it in `texts` (with a title and
`source_type='paste'`), runs `analyze()`, and returns tokens. Everything in the rest of Phase 4
(POS filter, dedupe, triage) operates on the text this step captures, so the auto-vocab pipeline
can be built and tested entirely on pasted text before a single line of scraping.

**Specifics:** `POST /import/paste {title, text}` → persists a `texts` row (`source_type='paste'`,
`raw_text`, `created_at`), returns `{text_id, tokens}`. Caches the analysis JSON in `texts.analysis`.

**Red — write the test:** `tests/test_import.py`:
- `test_paste_persists_text` *(contract)*: posting article text creates one `texts` row with
  `source_type='paste'` and the raw text intact.
- `test_paste_returns_analysis` *(golden)*: the response tokens match `analyze(text)`.
- Run → **red**.

**Green — make it pass:** add the route + `texts` insert; reuse `analyze`.

**Why it matters:** The always-works intake path; building the auto-vocab pipeline on top of it
means none of that logic is blocked on flaky fetching.

**Gate:** the paste tests pass. **Faithfulness:** store the wrong `source_type` →
`test_paste_persists_text` goes red.

**Commit:** `feat(import): tier-1 paste intake`

### Step 4.2 — POS filter (content words only)

**Goal:** `is_content_word(token)` keeping nouns/verbs/adjectives/adverbs and dropping particles,
auxiliaries, punctuation, and bare numbers.

**What we're building (read this first).** A news article is mostly grammatical glue — particles,
copulas, punctuation — that you don't want cluttering your vocab inbox. The POS filter is a simple
rule over Sudachi's POS tags that keeps only **content words** (the ones worth learning) and drops
the rest. It's a pure function over the tag you already capture, so it's trivially testable and a
high-leverage piece of the "don't dump junk on me" promise.

**Specifics:** `is_content_word(pos)` returns `True` iff `pos[0]` ∈ {`名詞` noun, `動詞` verb, `形容詞`
adjective, `副詞` adverb}, with carve-outs to drop `名詞-数詞` (bare numbers) and any `記号`/`補助記号`
(punctuation/symbols). Particles (`助詞`) and auxiliaries (`助動詞`) return `False`.

**Red — write the test:** `tests/test_intake.py`:
- `test_keeps_content_drops_particles` *(golden)*: **worked example** — analyzing `猫が魚を食べた`,
  `is_content_word` keeps `猫`/`魚`/`食べる` and drops `が`/`を`/the past auxiliary.
- `test_drops_numbers_and_punct` *(contract)*: a bare number token and a `。` token are dropped.
- Run → **red**.

**Green — make it pass:** write `server/importer/vocab_intake.py::is_content_word`.

**Why it matters:** This is what makes the triage list *learnable* — content words only, not the
40% of any sentence that's grammatical particles.

**Gate:** the filter tests pass. **Faithfulness:** include `助詞` in the keep-set →
`test_keeps_content_drops_particles` goes red (particles leak through).

**Commit:** `feat(intake): POS filter for content words`

### Step 4.3 — `vocab_intake`: dedupe + lookup + frequency

**Goal:** From analyzed text, produce the **new candidates** — content words not already in
`vocab`, with meanings attached and frequency counted.

**What we're building (read this first).** This is the auto-vocabulary brain. Given an analyzed
text it: filters to content words (4.2), **dedupes by lemma against existing `vocab`** (so anything
you already have — at any status — is not "new"), attaches meanings via jamdict, and counts
occurrences so the candidate list can be **frequency-sorted** (learn the highest-value words
first). The two invariants: a lemma already in `vocab` never appears as a candidate, and the same
lemma appearing five times in the article is one candidate with `frequency == 5`.

**Specifics:** `collect_candidates(conn, tokens) -> list[Candidate]` where `Candidate =
{lemma, reading, meanings, pos, frequency}`. Drop non-content words, drop lemmas present in `vocab`,
group remaining by lemma counting occurrences, attach `lookup_meanings`, sort by frequency desc.

**Red — write the test:** `tests/test_intake.py`:
- `test_excludes_known_vocab` *(invariant)*: with `食べる` already in `vocab`, analyzing a text
  containing `食べた` yields **no** `食べる` candidate.
- `test_dedupes_and_counts_frequency` *(invariant)*: **worked example** — a text where `猫` appears
  three times yields one `猫` candidate with `frequency == 3`.
- `test_candidates_sorted_by_frequency` *(contract)*: a more-frequent lemma sorts before a rarer one.
- Run → **red**.

**Green — make it pass:** write `vocab_intake.py::collect_candidates` (preload existing lemmas into
a set for an O(1) membership test).

**Why it matters:** This is the engine of the headline feature: it turns a wall of text into a
short, ranked list of words actually worth your time.

**Gate:** the intake tests pass. **Faithfulness:** skip the "already in vocab" filter →
`test_excludes_known_vocab` goes red.

**Commit:** `feat(intake): new-candidate collection with dedupe + frequency`

### Step 4.4 — Triage screen (Keep / Already-know)

**Goal:** Present candidates frequency-sorted; "Keep" saves a word (status→`learning`), "Already
know" records it as `known` so it never resurfaces.

**What we're building (read this first).** The draft plan is emphatic: **triage, don't dump.** A
single article yields ~40 candidates, many you half-know, and auto-adding all of them would
poison your review deck. So candidates go to a triage screen, frequency-sorted, with two actions
per word: **Keep** (creates a `vocab` row with `status='learning'` — and, once Phase 5 exists, an
FSRS card) or **Already know** (creates a `vocab` row with `status='known'`, which permanently
suppresses it from future candidate lists via the Step 4.3 filter). Each decision shrinks future
imports.

**Specifics:** `POST /triage {lemma, decision: "keep"|"known", …}` upserts `vocab` with the
matching `status`. The endpoints return the resulting status. (Card creation is added in Step 5.5;
keep the seam.)

**Red — write the test:** `tests/test_import.py`:
- `test_keep_sets_learning` *(contract)*: "keep" on `猫` creates `vocab` with `status='learning'`.
- `test_already_know_suppresses_future` *(invariant — the point)*: marking `猫` `known`, then
  re-running `collect_candidates` on a text containing `猫`, yields **no** `猫` candidate.
- Run → **red**.

**Green — make it pass:** add the triage routes; add `web/import.js` triage UI rendering the sorted
candidates with Keep/Already-know buttons.

**Why it matters:** Triage is what keeps the SRS deck full of *useful* cards instead of 40 noisy
ones per article; the suppression invariant is the compounding benefit over time.

**Gate:** the triage tests pass. **Faithfulness:** have "Already know" set `status='learning'` →
`test_already_know_suppresses_future` goes red (the word resurfaces).

**Commit:** `feat(import): triage screen with keep/already-know`

### Step 4.5 — Tier-2 URL fetch + extraction + encoding

**Goal:** Fetch a URL, extract the main article text with trafilatura, and correctly decode
Shift-JIS sources.

**What we're building (read this first).** Now automate the friendly case: given a URL, download
the page, run it through **trafilatura** to strip nav/ads/boilerplate and return clean article
text, then feed that into the same intake pipeline. The trap the draft plan flags: many Japanese
sources — especially **Aozora Bunko** — are **Shift-JIS**, not UTF-8, so you must detect/convert
encoding on the way in or you get mojibake. You test extraction and decoding on **saved HTML
fixtures** (no live network in the test suite), keeping tests fast and deterministic.

**Specifics:** `fetch_and_extract(url) -> str` downloads, detects encoding (don't assume UTF-8;
handle Shift-JIS), and runs trafilatura. In tests, inject saved HTML bytes rather than hitting the
network. `POST /import/url {url}` reuses the paste pipeline on the extracted text.

**Red — write the test:** `tests/test_fetch.py`:
- `test_shift_jis_decodes` *(golden — the trap)*: **worked example** — a small Shift-JIS-encoded
  byte fixture containing `日本語` decodes to the correct kanji (not mojibake).
- `test_extraction_strips_boilerplate` *(behavioural)*: a saved HTML fixture with nav + article
  yields text containing the article body and **not** the nav link text.
- Run → **red**.

**Green — make it pass:** write `server/importer/extract.py` (encoding detection + trafilatura) and
`sources.py::UrlSource`; wire the route.

**Why it matters:** Automates the common path while sidestepping the #1 Japanese-text import bug
(Shift-JIS mojibake); fixture-based tests keep the suite offline and fast.

**Gate:** the fetch tests pass. **Faithfulness:** force `decode("utf-8")` →
`test_shift_jis_decodes` raises/garbles → red.

**Commit:** `feat(import): tier-2 URL fetch with extraction + Shift-JIS`

### Step 4.6 — Tier-3 in-app browser "Import this page"

**Goal:** For JS-heavy or bot-blocking sites, let the user browse to an article in an in-app
browser and grab text from the already-rendered DOM.

**What we're building (read this first).** Some sites render with JavaScript or block bots, so
fetching their raw HTML gets you nothing. The draft plan's user-driven answer: an in-app browser
tab where *you* navigate to the article like a normal reader (the JS has run, and it's a real human
in a real browser — effectively Reader Mode), then click **"Import this page"** to extract text
from the live DOM. The engine-side work is small — accept the rendered HTML/text the webview hands
back and run it through the same extract→intake pipeline — so the test targets that handoff.

**Specifics:** `POST /import/dom {html}` (or rendered text) runs `extract` + the intake pipeline,
identical to tier-2 from the point text exists. The in-app browser is a pywebview tab with an
"Import this page" button that posts `document.documentElement.outerHTML`.

**Red — write the test:** `tests/test_import.py`:
- `test_dom_import_runs_pipeline` *(contract)*: posting rendered HTML for an article yields the same
  candidate list as pasting that article's clean text.
- Run → **red**.

**Green — make it pass:** add the `/import/dom` route reusing `extract`; add the browser tab +
button to the front end.

**Why it matters:** This is the escape hatch for hard sites, and it stays on the right side of the
etiquette line (a person reading one article, not a bulk scraper).

**Gate:** the DOM-import test passes; manually, browsing to an article and clicking "Import this
page" produces candidates. **Faithfulness:** bypass `extract` and feed raw HTML to intake →
boilerplate/nav words appear as candidates → the equivalence test goes red.

**Commit:** `feat(import): tier-3 in-app browser DOM import`

---

## Phase 5 — Spaced repetition (FSRS)

Add the `cards`/`review_logs` tables and the FSRS scheduler. **Deliverable:** real Anki-style
study driven by FSRS. (Use the MIT-licensed `fsrs` package — never Anki's AGPL source; DRAFT_PLAN
§1.)

### Step 5.1 — `cards` + `review_logs` schema

**Goal:** Add the `cards` and `review_logs` tables, with `review_logs` populated from day one.

**What we're building (read this first).** Scheduling state lives separately from linguistic
content: a `cards` row holds exactly the fields an FSRS `Card` carries (`state`, `due`, `stability`,
`difficulty`, `last_review`, `reps`, `lapses`) and links to a `vocab` row; a `review_logs` row
records every rating with its timestamp. The draft plan stresses keeping `review_logs` **from day
one even before anything reads them**, because you need the history later to optimize FSRS — so you
build the table now and write to it from the first review.

**Specifics:** `cards(id, vocab_id FK, state, due, stability, difficulty, last_review, reps, lapses)`
and `review_logs(id, card_id FK, rating, reviewed_at)` per DRAFT_PLAN §4. Extend `db.connect` to
create them.

**Red — write the test:** `tests/test_db.py`:
- `test_cards_and_logs_schema` *(contract)*: both tables exist with the FSRS-owned columns and the
  FK relationships.
- Run → **red**.

**Green — make it pass:** add the `CREATE TABLE` statements to `server/db.py`.

**Why it matters:** Separating scheduling from vocabulary (and logging reviews from the start) is
what makes FSRS persistence clean and future optimization possible.

**Gate:** the schema test passes. **Faithfulness:** omit `stability` from `cards` → a later
persistence test (Step 5.3) can't round-trip → red.

**Commit:** `feat(db): cards + review_logs schema`

### Step 5.2 — Scheduler wrapper (FSRS `review_card`)

**Goal:** `review(card, rating, now) -> (card, log)` wrapping py-fsrs's `Scheduler.review_card`.

**What we're building (read this first).** This wraps the modern FSRS scheduler. py-fsrs exposes a
`Scheduler` whose `review_card(card, rating)` takes a `Card` and a `Rating`
(`Again`/`Hard`/`Good`/`Easy` = 1–4) and returns an **updated card** plus a **review log**. Your
wrapper is a thin, deterministic seam over it that takes an injected `now` so tests are reproducible.
The properties that must hold for *any* correct scheduler: after a review the card's `due` is
**strictly in the future** (after `now`), `reps` increments, and a harder rating schedules the card
**sooner** than an easier one.

**Specifics:** `scheduler = Scheduler()`; `review(card, rating, now)` calls
`scheduler.review_card(card, rating)`. `Rating.Again=1 … Rating.Easy=4`. A fresh card is `Card()`.
Inject `now` for determinism.

**Red — write the test:** `tests/test_scheduler.py`:
- `test_due_in_future_and_reps_increment` *(invariant)*: reviewing a fresh card with `Good` returns
  a card whose `due > now` and `reps == 1`.
- `test_again_schedules_sooner_than_easy` *(invariant — the ordering)*: **worked example** — from
  identical fresh cards, the `due` after `Again` is **earlier** than the `due` after `Easy`.
- Run → **red**.

**Green — make it pass:** write `server/scheduler.py::review` over `fsrs.Scheduler`.

**Why it matters:** This is the learning algorithm. The ordering invariant (`Again` sooner than
`Easy`) is the behaviour that *defines* spaced repetition; pinning it catches a swapped-rating bug
instantly.

**Gate:** the scheduler tests pass. **Faithfulness:** map `Again`→`Rating.Easy` and vice-versa →
`test_again_schedules_sooner_than_easy` goes red.

**Commit:** `feat(scheduler): FSRS review wrapper`

### Step 5.3 — Card persistence round-trip

**Goal:** Persist exactly the fields the FSRS `Card` holds, and prove a saved-then-loaded card
schedules identically to the in-memory one.

**What we're building (read this first).** The subtle correctness risk in any SRS is *partial
persistence*: if you save `due` but forget `stability`, a reloaded card schedules differently than
it should and the algorithm silently degrades. So you persist **every** FSRS-owned field and prove
it with a **round-trip**: build a card, review it, save it, load it, review the loaded copy and the
in-memory copy with the same rating and `now`, and assert the two results are identical. That
equality is the guarantee that nothing was dropped on the way to disk.

**Specifics:** `save_card(conn, vocab_id, card)` and `load_card(conn, card_id) -> Card`
serialize/deserialize all of `state, due, stability, difficulty, last_review, reps, lapses`
(py-fsrs cards also offer `to_dict()`/`from_dict()` — fine to use). Round-trip equality is checked
*through a subsequent review*, not just field equality.

**Red — write the test:** `tests/test_db.py`:
- `test_card_round_trip_schedules_identically` *(round-trip — the crux)*: review a fresh card once,
  save, load; reviewing the loaded card and the original with the same rating + `now` yields equal
  `due`/`stability`/`difficulty`.
- Run → **red**.

**Green — make it pass:** write `save_card`/`load_card` persisting every field.

**Why it matters:** Dropping even one FSRS field corrupts scheduling invisibly; the
review-through-round-trip test is the only way to catch it.

**Gate:** the round-trip test passes. **Faithfulness:** stop persisting `stability` (default it on
load) → `test_card_round_trip_schedules_identically` goes red.

**Commit:** `feat(db): full FSRS card persistence (round-trip safe)`

### Step 5.4 — Review screen + endpoints

**Goal:** Endpoints to fetch the due queue and submit a rating, with a review UI: show word →
reveal meaning → Again/Hard/Good/Easy.

**What we're building (read this first).** The study loop. `GET /review/queue` returns cards whose
`due <= now` (joined to their vocab for display); `POST /review/answer {card_id, rating}` calls the
scheduler wrapper, persists the updated card, and **writes a `review_logs` row**. The front end
shows the word, reveals the reading + meaning on click, then offers the four rating buttons. The
behaviour worth testing end-to-end: answering a due card removes it from the immediate queue and
logs the review.

**Specifics:** `GET /review/queue?now=…` → due cards; `POST /review/answer {card_id, rating}` →
`review` + `save_card` + insert `review_logs`. The four buttons map to ratings 1–4.

**Red — write the test:** `tests/test_api.py`:
- `test_answer_advances_and_logs` *(behavioural)*: a due card answered `Good` is no longer in the
  immediate queue (its `due` moved out) and a `review_logs` row now exists for it.
- `test_queue_respects_due` *(contract)*: a card due in the future is absent from `GET /review/queue`.
- Run → **red**.

**Green — make it pass:** add the routes; add `web/review.js` (reveal + four buttons) and styling.

**Why it matters:** This is the studying experience itself; logging every answer (Step 5.1's table
earning its keep) is what enables later optimization.

**Gate:** the review tests pass; manually, you can study a deck. **Faithfulness:** skip the
`review_logs` insert → `test_answer_advances_and_logs` goes red on the log assertion.

**Commit:** `feat(review): due-queue + answer endpoints and review UI`

### Step 5.5 — "Keep" creates an FSRS card

**Goal:** Close the loop: triaging a candidate as "Keep" (Step 4.4) now also creates an FSRS card
so it enters the review queue.

**What we're building (read this first).** Until now "Keep" only set `vocab.status='learning'`;
this connects triage to study. When you Keep a word, the app also creates a fresh FSRS `Card`
(`Card()`), persists it linked to that vocab row, so the word shows up in the next review session.
The invariant that ties Phases 4 and 5 together: Keep creates **exactly one** card (Keeping the
same word twice doesn't create a second), while "Already know" creates **none**.

**Specifics:** extend the Step 4.4 triage handler so `decision="keep"` calls `save_card(conn,
vocab_id, Card())` once; `decision="known"` creates no card. Guard against double-Keep creating a
duplicate card.

**Red — write the test:** `tests/test_import.py`:
- `test_keep_creates_one_card` *(invariant)*: Keeping `猫` creates exactly one `cards` row for it;
  Keeping `猫` again does not create a second.
- `test_known_creates_no_card` *(contract)*: "Already know" on `犬` creates zero cards.
- Run → **red**.

**Green — make it pass:** add card creation to the Keep branch of the triage handler.

**Why it matters:** This is the seam that makes the whole app one loop: *read → collect → triage →
study*. Guarding against duplicate cards keeps the deck clean.

**Gate:** both tests pass; manually, a Kept word appears in the review queue. **Faithfulness:**
create a card on the `known` branch too → `test_known_creates_no_card` goes red.

**Commit:** `feat(srs): Keep in triage creates an FSRS card`

---

## Phase 6 — Polish & packaging (pick what you need)

Each step is self-contained; do them in any order. **Deliverable:** a double-clickable app on
Windows and Linux, plus the refinements that make daily use pleasant.

### Step 6.1 — Per-kanji furigana alignment

**Goal:** Align readings to individual kanji (食(た)べる) instead of over the whole word.

**What we're building (read this first).** The naive whole-word ruby from Step 2.2 is *correct* but
ugly for mixed kanji/kana words: `食べる` shows `食べる(たべる)` instead of `食(た)べる`. This step splits a
word into kanji/kana runs and distributes the reading so each kanji run gets only its share. It's
self-contained polish — explicitly deferred here so it never blocked the working reader. The clean
oracles: a pure-kanji word is unchanged (`都庁→とちょう` over the whole thing is already per-"run"), and
the kana tail of a mixed word carries **no** ruby.

**Specifics:** `align_ruby(surface, reading_hiragana) -> list[(base, rt|None)]`: segment the surface
into kanji vs kana runs; the trailing/embedded kana (okurigana) match themselves and are stripped
from the reading, leaving the kanji run its reading. Handle the common cases; fall back to
whole-word ruby when alignment is ambiguous.

**Red — write the test:** `tests/test_render.py`:
- `test_aligns_okurigana` *(golden)*: **worked example** — `align_ruby("食べる", "たべる")` puts `た` over
  `食` and leaves `べる` as plain kana.
- `test_pure_kanji_unchanged` *(invariant)*: `align_ruby("都庁", "とちょう")` puts the whole reading over
  the whole word.
- `test_ambiguous_falls_back` *(contract)*: a word the aligner can't confidently split falls back to
  whole-word ruby (never drops or corrupts the reading).
- Run → **red**.

**Green — make it pass:** write the alignment helper; have `render_ruby` use it.

**Why it matters:** It's the difference between "works" and "looks like a real reader"; isolating it
as a late, well-tested task is exactly the draft plan's guidance.

**Gate:** the alignment tests pass. **Faithfulness:** put the whole reading over the first kanji
only → `test_aligns_okurigana` goes red (`べる` would get ruby it shouldn't).

**Commit:** `feat(render): per-kanji furigana alignment`

### Step 6.2 — FSRS parameter optimization on your own logs

**Goal:** Re-fit the FSRS parameters from your accumulated `review_logs` and use them in the
scheduler.

**What we're building (read this first).** FSRS ships with sensible default parameters, but once
you have review history it can fit parameters to *your* memory, needing fewer reviews for the same
retention. py-fsrs exposes an optimizer that takes your logged reviews and returns tuned parameters;
you feed those into the `Scheduler`. This is why Step 5.1 insisted on logging from day one. The
testable contract: optimization needs a minimum amount of history (degrade gracefully below it), and
the tuned scheduler still satisfies the Step 5.2 invariants.

**Specifics:** `optimize_parameters(review_logs)` → parameter set fed to `Scheduler(parameters=…)`.
Below a minimum review count, keep the defaults (don't crash). Re-optimize roughly monthly.

**Red — write the test:** `tests/test_scheduler.py`:
- `test_optimized_scheduler_keeps_invariants` *(invariant)*: after optimizing on a synthetic log,
  the resulting scheduler still gives `due > now` and `Again` sooner than `Easy`.
- `test_insufficient_history_uses_defaults` *(edge)*: with too few logs, optimization returns the
  defaults instead of raising.
- Run → **red**.

**Green — make it pass:** write `server/scheduler.py::optimize_parameters` over py-fsrs's optimizer;
persist the parameters.

**Why it matters:** Personalized parameters are FSRS's core advantage; the invariant test ensures
tuning never breaks the fundamental scheduling behaviour.

**Gate:** the optimization tests pass. **Faithfulness:** feed the optimizer an empty log and assert
it still returns usable defaults — if it raises, the graceful-degradation path is missing.

**Commit:** `feat(scheduler): optimize FSRS parameters from review logs`

### Step 6.3 — Stats dashboard

**Goal:** Compute reviews/day, accuracy, and retention from `review_logs`, and show them.

**What we're building (read this first).** A dashboard turns your logged history into motivation and
insight: how many reviews per day, what fraction you got right (accuracy), and your true retention.
These are pure aggregations over `review_logs` (and `cards`), so the computation is fully testable
on synthetic data before any chart exists — the chart is just a view over numbers you've already
proven correct.

**Specifics:** `compute_stats(conn, now) -> {reviews_per_day, accuracy, retention, …}` aggregating
`review_logs`. Accuracy = fraction of reviews rated ≥ `Good`. A `GET /stats` route serves it; the
front end charts it.

**Red — write the test:** `tests/test_stats.py`:
- `test_accuracy_from_logs` *(golden)*: **worked example** — a synthetic log of 3 `Good` and 1
  `Again` yields `accuracy == 0.75`.
- `test_reviews_per_day_buckets` *(contract)*: logs across two days bucket into the right daily
  counts.
- Run → **red**.

**Green — make it pass:** write `server/stats.py::compute_stats` and the route; add the dashboard view.

**Why it matters:** Visible progress is what keeps a study habit alive; computing the metrics from
logs (and testing them) means the dashboard never lies to you.

**Gate:** the stats tests pass. **Faithfulness:** count `Again` as correct → `test_accuracy_from_logs`
goes red (accuracy would read 1.0).

**Commit:** `feat(stats): study dashboard (reviews/day, accuracy, retention)`

### Step 6.4 — `.apkg` export via genanki

**Goal:** Export your vocab + scheduling as an Anki `.apkg` for phone review.

**What we're building (read this first).** So you can review on your phone in real Anki, you export
your deck as a `.apkg` file using the MIT-licensed **genanki** (never Anki's AGPL source — DRAFT_PLAN
§1). Each `vocab` row becomes a note (word → reading + meaning); the package is a real, valid
`.apkg`. The testable contract: the export writes a non-empty file with the right magic/structure and
one note per exported word.

**Specifics:** `export_apkg(conn, path)` builds a `genanki.Deck`, adds one `genanki.Note` per vocab
row, and writes a `.apkg`. A `GET /export/apkg` route streams the file.

**Red — write the test:** `tests/test_export.py`:
- `test_apkg_written_with_notes` *(contract)*: exporting a DB with 3 vocab rows produces a non-empty
  `.apkg` file; re-opening it (genanki/sqlite) shows 3 notes.
- Run → **red**.

**Green — make it pass:** write `server/export.py::export_apkg` over genanki; add the route.

**Why it matters:** Phone review is where most reps actually happen; a clean export unlocks it
without coupling to Anki's licensing.

**Gate:** the export test passes; the file imports into Anki. **Faithfulness:** write the deck with
zero notes → `test_apkg_written_with_notes` goes red on the note count.

**Commit:** `feat(export): genanki .apkg export`

### Step 6.5 — PyInstaller packaging (Windows + Linux)

**Goal:** Build a double-clickable app for both OSes, with the dictionaries bundled as data files
and found at runtime.

**What we're building (read this first).** The final payoff: a single binary a non-developer can
run. PyInstaller bundles the Python engine, the front end, and — the part that bites — the
**data**: SudachiDict and the JMdict database are each tens of MB and must ship as bundled data
files that the app can locate at runtime (a hard-coded dev path won't exist in the bundle). So the
code resolves data paths relative to the bundle, and a packaged-app smoke check confirms the
dictionaries actually load from there.

**Specifics:** a PyInstaller spec that includes `web/`, the SudachiDict data, and the JMdict
database as `datas`; resolve resource paths via `sys._MEIPASS` (bundled) vs. the source tree (dev).
Build on each target OS.

**Red — write the test:** `tests/test_packaging.py` + a manual gate:
- `test_resource_path_resolves` *(contract)*: the path-resolver returns an existing path for `web/`
  and the dictionary data in dev mode (and, by construction, under `sys._MEIPASS` when frozen).
- **Manual gate:** the built binary launches on Windows and Linux, and **analyzing a sentence in the
  packaged app returns meanings** — proving the bundled dictionaries were found at runtime.
- Run → **red**.

**Green — make it pass:** add the resource-path helper, the PyInstaller spec, and build scripts;
run the packaged app and confirm analysis works.

**Why it matters:** "Double-clickable on both OSes" is the deliverable; the bundled-data check is the
one packaging failure that passes every unit test yet breaks the shipped app.

**Gate:** the resolver test passes **and** the packaged app analyzes text with meanings on both OSes.
**Faithfulness:** hard-code a dev-only absolute path → the packaged app returns empty meanings
(dictionary not found) → the manual gate fails.

**Commit:** `build: PyInstaller packaging for Windows + Linux`

---

## Key facts & defaults (one place to look them up)

| Topic | Value / rule |
|---|---|
| **Dedupe identity** | `vocab.lemma` (dictionary form), `UNIQUE`; never the surface form |
| **Reading** | Sudachi gives **katakana**; convert once with `jaconv.kata2hira`; idempotent |
| **Token contract** | `{surface, reading_hiragana, lemma, meanings: list[str], pos, known: bool}` |
| **Tokenizer API** | `Dictionary().create()`; `m.surface()`, `m.dictionary_form()`, `m.reading_form()`, `m.part_of_speech()` |
| **POS major class** | `m.part_of_speech()[0]` ∈ {`名詞`,`動詞`,`形容詞`,`副詞`,`助詞`,`助動詞`,`記号`,…} |
| **Content words** | keep 名詞/動詞/形容詞/副詞; drop 助詞/助動詞/記号/bare 数詞 |
| **Dictionary** | `Jamdict().lookup(lemma).entries[*].senses[*].gloss`; miss → `[]`, never raise |
| **Furigana** | naive whole-word `<ruby>surface<rt>reading</rt></ruby>` first; per-kanji later; HTML-escape |
| **FSRS** | `fsrs.Scheduler`; `review_card(card, rating) -> (card, log)`; `Rating.Again/Hard/Good/Easy = 1–4`; fresh = `Card()` |
| **FSRS invariants** | after review `due > now`, `reps`+1, `Again` due < `Easy` due; persist **all** card fields |
| **Encoding** | detect on import; Aozora Bunko is often **Shift-JIS**, not UTF-8 |
| **Server** | FastAPI bound to **`127.0.0.1`** only |
| **Logs** | write `review_logs` from day one (needed for Step 6.2 optimization) |
| **Licensing** | use MIT `fsrs`/`genanki`; never Anki's AGPL source; JMdict is CC BY-SA (attribute if distributing) |

---

## Concept → Python component map

| Concept | Python home |
|---|---|
| Tokenize (surface/lemma/reading/POS) | `server/analyze.py::tokenize` |
| Katakana → hiragana | `server/analyze.py::to_hiragana` |
| Lemma → meanings | `server/dictionary.py::lookup_meanings` |
| Raw text → display tokens | `server/analyze.py::analyze` (+ cache) |
| Furigana ruby | `server/render.py::render_ruby` / `align_ruby` |
| HTTP boundary | `server/main.py` (FastAPI, `127.0.0.1`) |
| Schema + dedupe upsert | `server/db.py` (`texts`,`vocab`,`cards`,`review_logs`; `upsert_vocab`) |
| Paste / URL / DOM intake | `server/importer/sources.py`, `extract.py` |
| POS filter + candidate collection | `server/importer/vocab_intake.py` |
| FSRS scheduling + optimization | `server/scheduler.py` |
| Card persistence | `server/db.py` (`save_card`/`load_card`) |
| Stats | `server/stats.py` |
| Anki export | `server/export.py` (genanki) |
| Desktop launcher | `app.py` (pywebview + uvicorn) |

---

## Milestone checklist (tape this above your desk)

Each box flips only when its step's test was written first, seen to fail, is now green — *and you've
sabotaged the code to confirm the test can fail.*

- [ ] **Phase 0** — green pytest harness; tokenizer spike (surface ≠ lemma); jamdict lemma lookup; ADR written
- [ ] **Phase 1** — `analyze()` emits the full Token; katakana→hiragana; lemma→meanings (graceful miss); cache == fresh
- [ ] **Phase 2** — `/analyze` (localhost); naive ruby (escaped); pywebview reader; click-word popover
- [ ] **Phase 3** — `vocab.lemma UNIQUE`; **inflections dedupe to one row**; save-word; known-word styling
- [ ] **Phase 4** — paste intake; content-word filter; **candidates exclude known + frequency-sorted**; triage suppresses known; Shift-JIS fetch; DOM import
- [ ] **Phase 5** — cards/logs schema; **`Again` sooner than `Easy`**; **card round-trips schedule-identically**; review loop logs; Keep → one card
- [ ] **Phase 6** — per-kanji ruby; FSRS optimization keeps invariants; stats; `.apkg` export; **packaged app finds bundled dictionaries**
