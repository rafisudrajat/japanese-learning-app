# DEV-PLAN: Quiz Generation from Vocabulary & Imported Texts

**Status:** Investigation / feasibility (no code written yet)
**Date:** 2026-06-21
**Question:** Can we auto-generate quizzes (JLPT-styled, or simpler "guess the meaning in context") from the user's vocabulary and submitted Japanese texts?

**Short answer:** Yes — several useful quiz types are feasible **today, fully offline, with the data and libraries we already have**. The one thing you specifically asked for — *"guess which meaning fits, since a word can mean different things depending on context"* — is the hardest part, because it requires **word-sense disambiguation (WSD)**, which neither JMdict nor SudachiPy gives us. That piece needs either a heuristic, manual labeling, or an LLM. Everything else is straightforward.

---

## 1. What we have to work with

| Asset | Where | Useful for quizzes? |
|---|---|---|
| Tokenizer (surface, lemma, katakana reading, POS) | `server/analyze.py` via SudachiPy | ✅ Core — segments text, gives readings & POS |
| Dictionary glosses | `server/dictionary.py` → `jamdict.lookup()` | ✅ Source of meanings & distractors |
| Furigana renderer | `server/render.py` | ✅ Reuse to show reading-quiz / context sentences |
| Saved vocab (lemma, reading, `primary_meaning`, `pos`, `status`) | `vocab` table | ✅ Pool of "words the user is learning" |
| Imported texts (`raw_text`, `title`, `first_seen_text_id` link) | `texts` table | ✅ Source of authentic context sentences |
| FSRS review loop + logs | `server/scheduler.py`, `cards`/`review_logs` | ✅ Quiz results can feed the same scheduler |

### Key data gaps (these shape the roadmap)

1. **Only the first gloss is persisted.** `vocab.primary_meaning` stores `glosses[0]` only. The full meaning list is computed transiently during `/analyze` and `/import` and then thrown away. → For a meaning quiz we must either re-run `jamdict.lookup()` at quiz time (cheap, jamdict is loaded anyway) or store the full list.

2. **Sense boundaries are flattened.** `lookup_meanings()` does `[g for entry in ... for sense in entry.senses for g in sense.gloss]` — it collapses JMdict's *sense* structure into one flat list. JMdict actually groups glosses by sense (sense 1 = "to rise", sense 2 = "to get up", …) and each sense carries POS + usage tags. **This grouping is exactly what a "meaning depends on context" quiz needs**, and we are currently discarding it.

3. **No occurrence/sentence index.** We know a word's `first_seen_text_id`, but not *which sentence* it appeared in. To quiz "meaning in context" we must re-tokenize the stored `raw_text` and locate sentences containing the target lemma. Doable on demand (texts are short) or precomputed into an `occurrences` table.

4. **`vocab.pos` keeps only the major POS** (`pos[0]`, e.g. 名詞/動詞). Enough for "same-POS distractors", not for fine usage questions.

5. **No JLPT / frequency level.** JMdict has *priority* tags (`news1`, `ichi1`, `nf01`–`nf48`) that jamdict exposes — usable as a commonness proxy for difficulty grading and for picking plausible distractors. True JLPT N5–N1 tagging would need an external word list (future).

---

## 2. Quiz types, ranked by feasibility

JLPT's vocabulary/grammar section is itself a menu of question formats. Mapping them to our data:

| # | Quiz type | JLPT analogue | Feasible now? | Needs |
|---|---|---|---|---|
| A | **Reading quiz** — show kanji word, pick correct hiragana | 漢字読み | ✅ Yes | readings (have), distractor readings |
| B | **Meaning recall (MCQ)** — show word, pick English meaning | (recognition) | ✅ Yes | glosses + distractors from other vocab |
| C | **Cloze / fill-the-blank** — blank a word in a real sentence, pick the word that fits | 文脈規定 | ✅ Yes | stored texts + same-POS distractors |
| D | **Orthography** — show hiragana, pick correct kanji | 表記 | ✅ Yes | readings + kanji forms |
| E | **Meaning-in-context (recognition)** — highlight word in its sentence, pick *a* correct meaning, distractors = meanings of *other* words | 語彙 | ✅ Yes (weak form) | sense list + context sentence |
| F | **Meaning-in-context (disambiguation)** — *the* sense that fits this sentence, distractors = *other senses of the same word* | (true WSD) | ⚠️ Partial | sense grouping + a way to pick the correct sense |
| G | **Usage** — pick the sentence using the word correctly | 用法 | ❌ Hard | multiple correct/incorrect example sentences |
| H | **Full JLPT-style item w/ explanation** | exam-grade | ❌ Not offline | LLM generation |

**Your specific request maps to E (easy) and F (hard).** E is buildable now and already valuable. F is the "real" version and is the crux of section 4.

---

## 3. Recommended phased roadmap

### Phase 1 — Offline quiz engine (no new dependencies, no schema migration)
Build quiz types **A (reading)**, **B (meaning recall)**, and **C (cloze)**. These need nothing we don't already have.

- New module `server/quiz.py`:
  - `make_reading_question(vocab_row, pool)` → stem = kanji lemma, correct = its reading, 3 distractors = readings of other same-length/same-POS vocab.
  - `make_meaning_question(vocab_row, pool, dictionary)` → stem = lemma, correct = a gloss, distractors = glosses of other vocab (prefer same POS).
  - `make_cloze_question(text_row, vocab_row, tokenizer)` → re-tokenize `texts.raw_text`, find a sentence containing the lemma, replace surface with `____`, correct = the word, distractors = same-POS vocab.
  - Shared `pick_distractors(target, pool, n=3, same_pos=True)`.
- New endpoints (mirror existing style in `server/main.py`):
  - `GET /quiz/next?type=reading|meaning|cloze` → returns a question payload `{question_id, prompt, kind, choices[], context_html?}`.
  - `POST /quiz/answer` → `{question_id, choice}` → `{correct, explanation, correct_choice}`. Optionally write to `review_logs` so quizzes reinforce FSRS.
- New page `web/quiz.html` + `web/js/quiz.js` (clone the `review.js` fetch/render pattern; reuse `render_ruby` for furigana on cloze/context).
- Tests in `tests/test_quiz.py` (use the `TestClient` + `_reset_db` pattern from `tests/test_api.py`).

**Why first:** delivers a working quiz immediately, no risk to the offline-first design, and establishes the UI + scoring plumbing the later phases reuse.

### Phase 2 — Preserve sense structure + context linkage (offline, small schema work)
Unlock quiz type **E** and lay groundwork for **F**.

- **Stop flattening senses.** Add `lookup_senses(lemma, dictionary)` returning a structured list:
  `[{sense_index, pos_tags, misc_tags, glosses: [...]}, ...]`. Keep the existing flat `lookup_meanings()` for backward compatibility (it can call the new one).
- **Persist meanings.** Either add `vocab.senses_json TEXT` (JSON blob) or a `senses` table (`vocab_id, sense_index, pos_tags, glosses_json`). JSON blob is simplest and matches how `meanings` already travels as JSON in `render.py`.
- **Sentence/occurrence index.** Add helper `find_context_sentence(lemma, texts, tokenizer)` (segment on `。！？\n`, return the first/most-recent sentence containing the lemma + character offsets for highlighting). Optionally cache into an `occurrences(vocab_id, text_id, sentence, char_start, char_end)` table for speed.
- Quiz type **E**: highlight the word in its real sentence, ask "what does it mean here?", correct = any sense of the word, distractors = senses of other words. **Genuinely useful and 100% offline.**

### Phase 3 — True contextual disambiguation (quiz type F) — the hard part
This is the only piece that cannot be done well with JMdict alone. Three options, in increasing quality and cost:

1. **Heuristic (offline, free, low accuracy).** JMdict orders senses roughly by frequency, so sense 0 is the safe "correct" answer; build the *distractors* from the word's *other* senses. This makes a real "which of this word's meanings fits?" item, but the labeled-correct sense is just "the most common one," which may be wrong for a given sentence. Acceptable as a study aid, not as an exam.

2. **Local LLM via Ollama (offline-ish, free, medium accuracy).** Run a small model locally to read the sentence and pick which JMdict sense applies. Preserves the "no external service" principle but adds a heavy optional dependency and a model download. Good middle ground if offline is non-negotiable.

3. **Claude API (online, paid, high accuracy).** Send the sentence + the word's JMdict sense list and ask Claude to (a) pick the sense that fits and (b) optionally write a full JLPT-style item with explanation and distractors. This is the cleanest route to **exam-grade questions (types F, G, H)**.
   - Model fit: `claude-haiku-4-5` for cheap per-item WSD/generation; `claude-sonnet-4-6` if you want richer explanations.
   - **Design tension:** the README's core principle is *local-first, offline, no external APIs, localhost-only*. An LLM call breaks that. Recommend gating it behind an explicit opt-in setting (off by default), caching every generated question so it's a one-time cost per item, and keeping Phases 1–2 fully functional without it.

---

## 4. The core challenge, stated plainly

For *"guess the meaning of the word given context"* to have a **correct answer**, something must decide which of a word's multiple JMdict senses is the one used in that sentence. Our current stack (SudachiPy + JMdict) gives us the senses but **not the disambiguation**. So:

- **Want it now, offline, no AI?** → Build quiz type **E** (correct = any sense of the word; distractors = senses of *other* words). It tests "do you know this word's meaning in a real sentence" without needing WSD. This is the pragmatic version of your idea and I'd ship it in Phase 1–2.
- **Want true "which sense fits here?" (type F)?** → You need an LLM (Phase 3). That's the only reliable way to label the correct sense and to reach genuine JLPT quality with explanations.

## 5. Suggested next step

Start with **Phase 1** — it's low-risk, reuses every existing pattern (`analyze` → JSON endpoint → vanilla-JS page → `TestClient` tests), and gives you a usable quiz this week. Add the sense-structure + context work in **Phase 2** to get the "meaning in a real sentence" quiz you described. Decide on Phase 3 (LLM) only once you've felt how far the offline version gets you.

The rest of this document is the **test-first implementation roadmap** for that Phase 1 offline quiz engine.

---

# PART II — Offline Quiz Engine: A Test-First ROADMAP

This roadmap builds the **offline quiz engine** (types A reading, B meaning recall, C cloze from
§2) entirely on the data and libraries we already ship — SudachiPy, jamdict, FastAPI, vanilla JS.
No new dependencies, no schema migration, no network. The end goal is a `/quiz-page` where you
pick a quiz type and answer multiple-choice questions auto-generated from your own vocabulary and
imported texts.

It is written as a **test-driven (TDD) curriculum**. For every step you:

1. **Red** — write the test the step specifies, against a function/endpoint that does not exist
   yet, and run `pytest` so you watch it **fail for the right reason** (import error / 404 / wrong
   value) — not a typo in the test.
2. **Green** — write the smallest implementation that makes that test pass.
3. **(Refactor)** — clean it up while the test stays green.

You advance only when **both** are true: the test is *faithful* (it genuinely exercises the
behaviour — not a tautology you bent to make pass) **and** it is green.

---

## How we test: deterministic logic + dictionary oracles

Quiz generation looks random, but it is **deterministic logic over known data** — which makes it
unusually friendly to TDD once randomness is injected (never `import random` at module level;
always take a `random.Random(seed)`). Every test below uses one of these oracle types.

| Oracle | What it proves | Example |
|---|---|---|
| **Dictionary / golden** | A known fact from JMdict/SudachiPy is correct | `猫` reads `ねこ`; a gloss of `猫` contains `"cat"`; `"猫が魚を食べた。犬が走る。"` splits into 2 sentences |
| **Deterministic (seeded RNG)** | Same seed ⇒ identical question, so it is testable at all | `pick_distractors(target, pool, n=3, rng=Random(0))` returns one fixed, asserted list |
| **Invariant / property** | A rule *every* generated question must satisfy | the correct answer is always in `choices`; choices are unique; no distractor equals the answer; `len(choices) == 4` |
| **Contract** | An endpoint's response shape | `GET /quiz/next` returns `{question_id, kind, prompt, choices}`; mirrors the `TOKEN_FIELDS` shape test in `tests/test_api.py` |
| **Behavioural** | The whole flow actually works | `GET /quiz/next` → `POST /quiz/answer` with the correct index ⇒ `{correct: true}`; wrong index ⇒ `{correct: false}` |

**Why invariants matter here.** Distractor selection is the one place a "looks fine" implementation
quietly breaks: a distractor that *is* the right answer, a duplicate option, or fewer than 4 choices
all produce a quiz that looks plausible but is wrong. The invariant tests run those rules on every
generated question so they can't silently regress.

---

## The faithfulness check (read this twice)

A test that asserts nothing, asserts something always-true, or that you edited to stop failing, is
**not** a pass — it is a silent hole. Before you trust a green bar, **sabotage your own
implementation** (flip a comparison, delete a filter, hard-code an index) and confirm the test goes
red. Every step below names the specific sabotage to try. The classic trap in this codebase: a
distractor test that happens to pass because the tiny pool only had one POS — so each step's
faithfulness note tells you which line to break.

---

## How to read each step

Every step has the same shape:

> **Goal** — the one-sentence outcome.
>
> **What we're building (read this first)** — plain-English orientation: what the function/endpoint
> *is*, the job it does in the quiz engine, and each moving part in sentences — before any code.
>
> **Data & rules** — the exact inputs, outputs, and rules your test must assert, so you pin down the
> *true* answer rather than a guess.
>
> **Red — write the test** — the test file, the function/endpoint signature it pins down, the oracle
> type, the assertions, and a **worked example** (tiny concrete inputs and the value you expect
> back). End of Red = a test that **fails for the right reason** (the function doesn't exist yet).
>
> **Green — make it pass** — the implementation to write, plus the one subtlety most likely to bite.
>
> **Why it matters** — the transferable skill.
>
> **Gate** — the command that must pass, plus the **faithfulness sabotage**.
>
> **Commit** — a [Conventional Commits](https://www.conventionalcommits.org/) message. One green
> gate = one commit.

---

## Conventions for this codebase (match the existing code)

- **Python 3.11+**, `snake_case`, full type hints, **ruff line-length 100** (`ruff check . && ruff format .`).
- **Separate pure logic from I/O.** All quiz *generation and grading* lives in `server/quiz.py` as
  **pure functions over plain dataclasses** — no `sqlite3`, no `jamdict`, no HTTP. The API layer in
  `server/main.py` does the DB reads and calls into `quiz.py`. This is what makes the logic unit-testable
  without a server. (Mirror how `analyze.py` is pure and `main.py` wraps it.)
- **Determinism is mandatory.** Every function that chooses options takes an injected
  `rng: random.Random`. Tests pass `random.Random(0)`; the endpoint passes `random.Random()`. Never
  call the global `random` module.
- **Dictionary access stays where it already is.** Reuse `lookup_meanings()` from `server/dictionary.py`
  and the shared `tokenizer` from `server/main.py`. The pure layer receives *already-looked-up* strings.
- **Tests:** pure logic in `tests/test_quiz.py` using the `conftest.py` fixtures (`tokenizer`,
  `dictionary`, `db`); endpoints extend the `TestClient` + `dependency_overrides[get_db]` + `_reset_db()`
  pattern from `tests/test_api.py`.
- **Frontend:** one page `web/quiz.html` + one script `web/js/quiz.js`, styled by the shared
  `/static/css/style.css`, served by a `GET /quiz-page` `FileResponse` route (exactly like
  `/review-page`). A `<a href="/quiz-page">Quiz</a>` nav link is added to **every** existing page
  (`index/import/vocab/review/stats`), matching their identical `<nav>` block.
- **One green gate = one commit.** Run `pytest -q` from the project root after every step.

---

## Phase 0 — Foundations: a trustworthy test loop

No quiz code yet. Make the build/test loop honest and record the design decisions everything else
assumes.

### Step 0.1 — Green baseline

**Goal:** `pytest -q` runs the existing 48 tests green, so every later Red/Green is measured against
a known-good baseline.

**What we're building (read this first).** TDD only works if "all green" is a state you can trust
and return to. Before writing any quiz code, run the full suite and watch it pass, and confirm the
`conftest.py` fixtures you'll lean on (`tokenizer`, `dictionary`, `db`) actually resolve — the
session-scoped `tokenizer`/`dictionary` are slow to build, so a misconfigured fixture shows up here,
not mid-feature.

**Data & rules:** none — pure plumbing.

**Red — write the test:** no new test; the "test" is running the suite from the project root:
```
pytest -q
```
The worked example of "red" here is any pre-existing failure or a fixture/import error — fix the
environment (`pip install -e ".[dev]"`) until it's green before continuing.

**Green — make it pass:** ensure the venv is set up and `pytest -q` reports all existing tests pass
and *names* the test files.

**Why it matters:** A runner that errors on collection but you ignore is worse than a failing test —
it hides every later regression.

**Gate:** `pytest -q` green. **Faithfulness:** temporarily break one `assert` in
`tests/test_api.py` → the bar goes red → revert. (If breaking it doesn't turn the bar red, your
runner isn't running it — fix that first.)

**Commit:** `chore(test): confirm green baseline before quiz work`

### Step 0.2 — Deterministic test helpers (built test-first)

**Goal:** Build the two helpers every later quiz test calls — a seeded RNG convention and a
`make_pool(...)` builder of fake `VocabEntry` rows — and **meta-test** them so a question pool you
don't trust can't make later green bars lie.

**What we're building (read this first).** Almost every quiz test needs (a) a small pool of vocab
to draw distractors from and (b) reproducible randomness. You write a tiny `VocabEntry` dataclass
(`lemma, reading, meaning, pos`) and a `make_pool(specs)` test helper that turns terse tuples into
entries, then prove the determinism property you're about to rely on everywhere: **the same seed
yields the same selection**. If that property is false, no seeded golden test below means anything.

**Data & rules:**
- `VocabEntry(lemma: str, reading: str, meaning: str, pos: str)` — the plain, DB-free unit the pure
  layer operates on.
- Determinism contract: any function taking `rng: random.Random` returns identical output for
  `random.Random(0)` across runs and machines.

**Red — write the test:** in `tests/test_quiz.py`:
- `test_seeded_rng_is_reproducible` *(deterministic)*: **worked example** — call a trivial
  `sample_one(pool, rng)` (or `pick_distractors`, once it exists in 1.1) twice with fresh
  `random.Random(0)` and assert the two results are identical, and that `random.Random(1)` differs.
- `test_make_pool_shape` *(contract)*: `make_pool([("猫","ねこ","cat","名詞")])` yields one
  `VocabEntry` with those exact fields.
- Run → **red** (`VocabEntry` / helper don't exist).

**Green — make it pass:** add `VocabEntry` to `server/quiz.py` and `make_pool` to `tests/test_quiz.py`
(or a `tests/quiz_helpers.py` imported by it).

**Why it matters:** Your oracles are only as trustworthy as the fixtures that feed them; pinning
determinism now means every seeded golden below is meaningful.

**Gate:** the helper tests pass. **Faithfulness:** make the helper ignore its `rng` and call global
`random.shuffle` → `test_seeded_rng_is_reproducible` goes red (two seed-0 runs diverge).

**Commit:** `test(quiz): add VocabEntry + deterministic pool/RNG helpers`

### Step 0.3 — Design decisions (ADR)

**Goal:** Decide, once and in writing, the quiz data model and how grading works, so Phases 1–5 are
mechanical "fill in the function" work.

**What we're building (read this first).** A short ADR (`doc/adr-002-quiz-engine.md`) fixing the
handful of decisions every later step leans on: the `Question` shape, how the correct answer is
represented and graded, how the API remembers a question between `/quiz/next` and `/quiz/answer`,
and where randomness is injected.

**Decisions to record:**
- **`Question` dataclass** (frozen): `kind: str` (`"reading" | "meaning" | "cloze"`), `prompt: str`,
  `choices: tuple[str, ...]`, `answer_index: int`, `context_html: str | None = None`,
  `target_lemma: str = ""`. One shape for all three quiz types keeps the API and UI uniform.
- **Choice count:** 1 correct + 3 distractors = **4 choices**, shuffled; `answer_index` records where
  the correct one landed.
- **Grading is a pure function** `grade(question, choice_index) -> bool` returning
  `choice_index == question.answer_index`. No I/O.
- **Cross-request state:** `/quiz/next` mints a `question_id` (uuid4) and the server caches the
  generated `Question` in an **in-process dict** (`_pending: dict[str, Question]`); `/quiz/answer`
  looks it up and grades. Rationale: single-user localhost app, no need to persist; the answer is
  never sent to the client, so the UI can't trivially reveal it. (Record the tradeoff: a server
  restart drops an in-flight question — acceptable.)
- **RNG injection:** every generator takes `rng: random.Random`; the endpoint constructs a fresh
  `random.Random()` per request, tests pass `random.Random(0)`.
- **Scope:** offline only (types A/B/C). Sense-structure (type E) and LLM (type F) are out of scope
  here and tracked in §3 Phases 2–3.

**Checkpoint (not a unit test):** the ADR exists and the `Question` example is concrete enough to
paste into Step 2.1's test.

**Why it matters:** One recorded decision about grading + cross-request state turns the API phase
into a small unambiguous wiring job instead of a mid-stream argument with yourself.

**Gate:** ADR written; `Question` example concrete enough to copy into a later test.

**Commit:** `docs(adr): record quiz data model and grading conventions`

---

## Phase 1 — Distractor selection (the shared kernel)

One pure function underlies all three quiz types. Build it first and harden it — like a numerical
primitive every later step stands on.

### Step 1.1 — `pick_distractors`

**Goal:** Given a target word and a pool, choose `n` plausible wrong options — same part of speech
when possible, never the target, never duplicated, deterministic under a seed.

**What we're building (read this first).** A multiple-choice question is only as good as its wrong
answers. `pick_distractors` is the shared engine all three quiz types call: it filters the pool to
*other* words (excluding the target), **prefers same-POS** candidates so a noun question doesn't
offer a verb as a decoy, draws `n` of them with the injected RNG, and — when there aren't enough
same-POS words — *falls back* to filling the rest from other POS rather than returning too few. The
properties it must guarantee (exactly `n`, unique, target excluded) are exactly the ones that make a
question valid, so they're the heart of the test.

**Data & rules:**
- `pick_distractors(target: VocabEntry, pool: list[VocabEntry], n: int, rng: random.Random, same_pos: bool = True) -> list[VocabEntry]`.
- Exclude any entry whose `lemma == target.lemma`.
- Prefer entries with `pos == target.pos`; if fewer than `n` exist, top up from the rest.
- Return **exactly `min(n, available)`** distinct entries; never the target; no duplicates.
- Deterministic for a given `rng`.

**Red — write the test:** in `tests/test_quiz.py`:
- `test_distractors_exclude_target` *(invariant)*: **worked example** — target `猫`, pool of 5 nouns
  incl. `猫`; `pick_distractors(猫, pool, 3, Random(0))` returns 3 entries, none `猫`, all distinct.
- `test_distractors_prefer_same_pos` *(invariant)*: pool with 4 nouns + 4 verbs, noun target ⇒ all 3
  distractors are nouns.
- `test_distractors_fallback_when_too_few_same_pos` *(invariant)*: pool with 1 other noun + 5 verbs,
  noun target, `n=3` ⇒ returns 3 (the 1 noun + 2 verbs), still excluding the target.
- `test_distractors_small_pool` *(edge)*: pool with only 2 usable entries, `n=3` ⇒ returns 2 (not a
  crash, not a duplicate).
- `test_distractors_deterministic` *(deterministic)*: two `Random(0)` calls give identical lists.
- Run → **red**.

**Green — make it pass:** implement `pick_distractors` in `server/quiz.py`. Subtlety: build the
same-POS and other-POS candidate lists *separately*, shuffle each with `rng`, then concatenate and
take `n` — so the same-POS preference and determinism both hold.

**Why it matters:** This is the kernel; every quiz type's quality and every invariant test downstream
rests on it being correct and reproducible.

**Gate:** the distractor tests pass. **Faithfulness:** delete the `lemma == target.lemma` exclusion →
`test_distractors_exclude_target` goes red.

**Commit:** `feat(quiz): add same-POS distractor selection`

---

## Phase 2 — The three offline quiz generators (pure functions)

Each is a pure function returning a `Question`. They share `pick_distractors` and the 4-choice
invariant.

### Step 2.1 — Reading quiz (type A: 漢字読み)

**Goal:** `make_reading_question(target, pool, rng)` — show a kanji word, ask for its hiragana
reading, with three other words' readings as decoys.

**What we're building (read this first).** The simplest quiz: the prompt is the target's kanji lemma
(e.g. `猫`), the correct choice is its reading (`ねこ`), and the distractors are *readings* of three
other words. Only words that actually contain kanji are eligible — a kana-only word's "reading" is
itself, which is no question — so the generator requires a kanji target. The correct reading is
inserted at a random position among the shuffled choices and `answer_index` records where.

**Data & rules:**
- `make_reading_question(target, pool, rng) -> Question` with `kind="reading"`, `prompt=target.lemma`.
- `choices` = the target's `reading` + 3 distractor readings (from `pick_distractors`), shuffled.
- `answer_index` points at the target's reading; `choices` are unique strings; `len == 4`.
- Precondition: `target.lemma` contains kanji (reuse `_contains_kanji` from `server/render.py`); a
  kana-only target raises `ValueError` (the caller skips it).

**Red — write the test:** in `tests/test_quiz.py`:
- `test_reading_question_golden` *(dictionary + deterministic)*: **worked example** — target
  `VocabEntry("猫","ねこ","cat","名詞")`, a fixed pool, `Random(0)` ⇒ `prompt=="猫"`,
  `"ねこ" in choices`, and `choices[answer_index] == "ねこ"`.
- `test_reading_question_invariants` *(invariant)*: `len(choices)==4`, all unique, `answer_index`
  in range, correct reading present exactly once.
- `test_reading_question_rejects_kana_only` *(edge)*: a kana-only target raises `ValueError`.
- Run → **red**.

**Green — make it pass:** implement `make_reading_question`; insert the correct reading at
`rng.randrange(4)` after collecting distractor readings.

**Why it matters:** Establishes the build-choices-then-shuffle-and-record-index pattern the other two
generators reuse.

**Gate:** the reading tests pass. **Faithfulness:** hard-code `answer_index = 0` → `*_golden` goes
red whenever the correct reading didn't land at index 0.

**Commit:** `feat(quiz): add reading (漢字読み) question generator`

### Step 2.2 — Meaning quiz (type B: recall)

**Goal:** `make_meaning_question(target, pool, rng)` — show a word, ask for its English meaning, with
three *other words'* meanings as decoys.

**What we're building (read this first).** The prompt is the word (lemma, optionally with reading),
the correct choice is one of the target's glosses, and the distractors are glosses belonging to
*different* words — crucially **not** other senses of the same word (that's the harder type F we're
deliberately not doing offline). Because the pure layer is DB/jamdict-free, the caller supplies each
`VocabEntry.meaning` already looked up (via `lookup_meanings` / `primary_meaning`).

**Data & rules:**
- `make_meaning_question(target, pool, rng) -> Question`, `kind="meaning"`, `prompt=target.lemma`.
- Correct choice = `target.meaning`; distractors = `pick_distractors(...)` then take their `.meaning`.
- Distractor meanings must differ from the correct meaning (drop collisions, top up if needed).
- 4 unique choices, `answer_index` correct.

**Red — write the test:**
- `test_meaning_question_golden` *(dictionary + deterministic)*: **worked example** — target `猫`
  with `meaning` containing `"cat"`, fixed pool, `Random(0)` ⇒ the correct choice's text is the cat
  gloss and `choices[answer_index]` equals it.
- `test_meaning_distractors_are_other_words` *(invariant)*: every distractor meaning belongs to a
  pool entry whose lemma ≠ target, and none equals the correct meaning.
- `test_meaning_question_invariants` *(invariant)*: 4 unique choices, index in range.
- Run → **red**.

**Green — make it pass:** implement `make_meaning_question`; reuse `pick_distractors`, then map to
`.meaning` and de-dupe against the correct answer.

**Why it matters:** This is the "do you know what this word means" quiz; keeping distractors from
*other words* is exactly what makes it offline-feasible (no WSD needed).

**Gate:** the meaning tests pass. **Faithfulness:** build distractors from the *target's own*
meaning string (split into fragments) instead of other words → `test_meaning_distractors_are_other_words`
goes red.

**Commit:** `feat(quiz): add meaning-recall question generator`

### Step 2.3 — Sentence segmentation + locate-and-blank

**Goal:** Two helpers the cloze quiz needs — split a text into sentences, and blank a target word
inside the sentence it appears in.

**What we're building (read this first).** A cloze question is a real sentence from an imported text
with one word replaced by `____`. Two pure helpers get us there. `split_sentences(text)` breaks text
on Japanese terminators (`。！？` and newlines) into a list of sentences. `blank_target(sentence,
target_lemma, tokenizer)` re-tokenizes the sentence, finds the token whose *lemma* matches the
target (so the inflected surface `食べた` is found for lemma `食べる`), and replaces that token's
**surface** with `____`, returning the blanked string and the surface that was removed. Matching by
lemma but blanking the surface is the subtle, must-test part.

**Data & rules:**
- `split_sentences(text: str) -> list[str]`: split on `。！？\n`, keep the terminator with its
  sentence, drop empties/whitespace-only.
- `blank_target(sentence, target_lemma, tokenizer) -> tuple[str, str]`: returns
  `(blanked_sentence, removed_surface)`; replaces the first token whose `dictionary_form()` equals
  `target_lemma`. Raises `ValueError` if the lemma isn't present.

**Red — write the test:** (these use the `tokenizer` fixture from `conftest.py`)
- `test_split_sentences_golden` *(golden)*: **worked example** —
  `split_sentences("猫が魚を食べた。犬が走る。")` == `["猫が魚を食べた。", "犬が走る。"]`.
- `test_blank_target_uses_surface_of_lemma` *(golden)*: **worked example** —
  `blank_target("猫が魚を食べた。", "食べる", tokenizer)` == `("猫が魚を____。", "食べた")` (lemma
  `食べる` matched, inflected surface `食べた` blanked).
- `test_blank_target_missing_raises` *(edge)*: a lemma not in the sentence raises `ValueError`.
- Run → **red**.

**Green — make it pass:** implement both in `server/quiz.py`. Subtlety: blank by the matched token's
`surface()` length/position, not by string-replacing the lemma (the lemma may not appear verbatim).

**Why it matters:** This is the bridge from "stored text" to "context question"; the lemma-match /
surface-blank distinction is exactly where a naive `str.replace` silently fails on inflected words.

**Gate:** the segmentation/blank tests pass. **Faithfulness:** blank by `sentence.replace(target_lemma,
"____")` → `test_blank_target_uses_surface_of_lemma` goes red (`食べる` isn't in the sentence, nothing
is blanked).

**Commit:** `feat(quiz): add sentence split + lemma-aware blanking`

### Step 2.4 — Cloze quiz (type C: 文脈規定)

**Goal:** `make_cloze_question(target, sentence, pool, tokenizer, rng)` — a real sentence with the
target blanked, asking which word fills the gap, with three same-POS words as decoys.

**What we're building (read this first).** Combine 1.1 + 2.3: take a sentence containing the target,
blank the target with `blank_target`, set the prompt to the blanked sentence, make the correct choice
the **target word** (its lemma/surface), and draw three same-POS distractor words. Optionally render
the surrounding sentence with furigana via `render_ruby` into `context_html` so the reader sees
readings on the non-blank kanji.

**Data & rules:**
- `make_cloze_question(target, sentence, pool, tokenizer, rng) -> Question`, `kind="cloze"`.
- `prompt` = blanked sentence (from `blank_target`); correct choice = the removed surface (or
  `target.lemma`); distractors = same-POS words from `pick_distractors`.
- 4 unique choices, `answer_index` correct; `context_html` optional (furigana-rendered sentence).

**Red — write the test:** (uses `tokenizer` fixture)
- `test_cloze_question_golden` *(golden + deterministic)*: **worked example** — target `魚`
  (`名詞`), sentence `"猫が魚を食べた。"`, fixed noun pool, `Random(0)` ⇒ `prompt == "猫が____を食べた。"`,
  `"魚" in choices`, `choices[answer_index] == "魚"`.
- `test_cloze_distractors_same_pos` *(invariant)*: all distractors share the target's POS.
- `test_cloze_question_invariants` *(invariant)*: 4 unique choices, index in range.
- Run → **red**.

**Green — make it pass:** implement `make_cloze_question` composing `blank_target` + `pick_distractors`.

**Why it matters:** This is the JLPT 文脈規定 format and the most "real" of the three — it tests the
word in authentic context drawn from the user's own reading.

**Gate:** the cloze tests pass. **Faithfulness:** put the *target* itself into the distractor list
(skip `pick_distractors`' exclusion) → `test_cloze_question_invariants` goes red (duplicate / answer
appears twice).

**Commit:** `feat(quiz): add cloze (文脈規定) question generator`

---

## Phase 3 — Grading (pure)

### Step 3.1 — `grade`

**Goal:** A pure `grade(question, choice_index) -> bool` plus the correct-answer text for feedback.

**What we're building (read this first).** Grading is trivial but deserves its own tested function so
the API and UI never re-implement it. It returns whether the chosen index matches `answer_index`, and
the API will pair it with `question.choices[answer_index]` so the UI can show "correct answer was X."

**Data & rules:** `grade(question, choice_index) -> bool` ≡ `choice_index == question.answer_index`;
out-of-range index ⇒ `False` (not an exception).

**Red — write the test:**
- `test_grade_correct_and_incorrect` *(closed-form)*: **worked example** — a `Question` with
  `answer_index=2`; `grade(q, 2) is True`, `grade(q, 0) is False`.
- `test_grade_out_of_range` *(edge)*: `grade(q, 99) is False`.
- Run → **red**.

**Green — make it pass:** implement `grade` in `server/quiz.py`.

**Why it matters:** A single source of truth for correctness keeps the endpoint and any future
FSRS-rating mapping consistent.

**Gate:** the grading tests pass. **Faithfulness:** change `==` to `!=` → both assertions in
`test_grade_correct_and_incorrect` go red.

**Commit:** `feat(quiz): add pure grade() function`

---

## Phase 4 — The API

Wire the pure engine to HTTP, mirroring the endpoint/model style in `server/main.py`.

### Step 4.1 — `GET /quiz/next`

**Goal:** Build a question from the user's saved vocab (+ imported texts for cloze) and return it,
caching the answer server-side.

**What we're building (read this first).** The endpoint reads the vocab pool from the DB, picks a
random learnable target, calls the matching generator from `quiz.py` with a fresh `random.Random()`,
stores the `Question` in `_pending` under a new `question_id`, and returns everything *except* the
answer index. For `type=cloze` it also needs a sentence: pull the target's `first_seen_text_id` text
(or any text containing the lemma), `split_sentences`, and pick one containing the target. If the
pool is too small to build 4 choices, return **HTTP 400** with a clear message.

**Data & rules:**
- `GET /quiz/next?type=reading|meaning|cloze` → `QuizQuestionResponse{question_id, kind, prompt,
  choices: list[str], context_html: str | None}` — **no `answer_index`**.
- Pool = `vocab` rows with `status` in `("learning","known")` mapped to `VocabEntry` (meaning =
  `primary_meaning`); reading-quiz targets filtered to kanji-containing lemmas; cloze targets filtered
  to those with an available sentence.
- Too few candidates ⇒ `HTTPException(400)`.

**Red — write the test:** extend `tests/test_api.py` (reuse `_reset_db`, `client`):
- `test_quiz_next_shape` *(contract)*: **worked example** — seed the DB with ~6 saved words, then
  `GET /quiz/next?type=meaning` returns 200 with keys `{question_id, kind, prompt, choices,
  context_html}`, `len(choices)==4`, and **no** `answer_index` key.
- `test_quiz_next_reading_prompt_has_kanji` *(invariant)*: `type=reading` prompt contains kanji.
- `test_quiz_next_too_few_vocab_400` *(edge)*: with only 1 saved word, returns 400.
- Run → **red**.

**Green — make it pass:** add the pydantic models + route to `server/main.py`; build the pool, call
the generator, stash in `_pending`, return the answer-free payload. Reuse the module-level `_tokenizer`
and `_get_dictionary()`.

**Why it matters:** This is the contract the UI codes against; hiding `answer_index` is what keeps the
quiz honest.

**Gate:** the `/quiz/next` tests pass. **Faithfulness:** include `answer_index` in the response model
→ `test_quiz_next_shape`'s "no answer_index key" assertion goes red.

**Commit:** `feat(api): add GET /quiz/next`

### Step 4.2 — `POST /quiz/answer`

**Goal:** Grade a submitted choice against the cached question and return the verdict + correct answer.

**What we're building (read this first).** The client posts the `question_id` and the chosen index.
The server looks up the cached `Question`, calls `grade`, and returns `{correct, correct_index,
correct_answer}` so the UI can highlight right/wrong. An unknown/expired `question_id` ⇒ 404.

**Data & rules:**
- `POST /quiz/answer` body `{question_id: str, choice_index: int}` →
  `{correct: bool, correct_index: int, correct_answer: str}`.
- Unknown `question_id` ⇒ `HTTPException(404)`. (Optionally: pop it from `_pending` so it can't be
  re-answered.)

**Red — write the test:**
- `test_quiz_answer_correct_flow` *(behavioural — the anchor)*: **worked example** —
  `GET /quiz/next`, then because the test can't see `answer_index`, post each index until one returns
  `correct: true`; assert exactly one index is correct and `correct_answer` matches `choices[correct_index]`.
  (Alternatively, expose the generator in a unit test to know the index; the behavioural form proves
  the round-trip.)
- `test_quiz_answer_unknown_id_404` *(edge)*: posting a random uuid ⇒ 404.
- Run → **red**.

**Green — make it pass:** add the route; look up `_pending[question_id]`, grade, return the verdict.

**Why it matters:** This closes the loop — generate → answer → verdict — and is the first end-to-end
proof the engine works through HTTP.

**Gate:** the `/quiz/answer` tests pass. **Faithfulness:** return `correct = not grade(...)` →
`test_quiz_answer_correct_flow` goes red (every index reports wrong).

**Commit:** `feat(api): add POST /quiz/answer`

### Step 4.3 — (Optional) feed results into FSRS

**Goal:** A correct/incorrect quiz answer optionally updates the word's FSRS card and writes a
`review_logs` row, so quizzing reinforces spaced repetition.

**What we're building (read this first).** Map the verdict to an FSRS `Rating` (e.g. wrong→`Again`,
right→`Good`) and reuse `scheduler.review` + `update_card` + the `review_logs` insert exactly as
`POST /review/answer` does. Gate it behind a request flag so plain quizzing without SRS side-effects
still works.

**Data & rules:** correct ⇒ `Rating.Good (3)`, incorrect ⇒ `Rating.Again (1)`; only when the target
has a card and the request opts in (`?count_as_review=true`).

**Red — write the test:**
- `test_quiz_answer_updates_review_log` *(behavioural)*: with `count_as_review=true`, answering a
  carded word adds exactly one `review_logs` row with the mapped rating.
- Run → **red**.

**Green — make it pass:** thread the optional FSRS update into `/quiz/answer`, reusing `load_card`/
`update_card`/`review`.

**Why it matters:** Unifies "quiz" and "review" so study effort counts once, toward the same schedule
and stats.

**Gate:** the review-log test passes. **Faithfulness:** map both verdicts to `Good` → assert the
*wrong*-answer case logged `Again`; it goes red.

**Commit:** `feat(api): optionally log quiz answers as FSRS reviews`

---

## Phase 5 — The web UI

### Step 5.1 — `quiz.html` + `quiz.js`

**Goal:** A `/quiz-page` that lets you pick a type, fetch a question, choose an answer, and see
right/wrong — mirroring `review.html`/`review.js`.

**What we're building (read this first).** Clone the review page's structure: a `GET /quiz-page`
`FileResponse` route, a `web/quiz.html` with the shared `<nav>` (now including a Quiz link) and the
shared stylesheet, and a `web/js/quiz.js` that `fetch`es `/quiz/next?type=…`, renders the prompt
(injecting `context_html` as HTML for cloze so furigana shows) and the four choices as buttons, posts
to `/quiz/answer`, then highlights the correct/incorrect choice and offers "Next". Add the
`<a href="/quiz-page">Quiz</a>` link to the `<nav>` of all five existing pages.

**Data & rules:** page served exactly like `/review-page`; JS uses the two endpoints from Phase 4;
cloze `context_html` is trusted local HTML from `render_ruby` (safe to inject).

**Red — write the test:** extend `tests/test_api.py`:
- `test_quiz_page_served` *(contract)*: `GET /quiz-page` returns 200 and `text/html`, and the body
  contains `quiz.js` (proving the right file is wired).
- Run → **red** (route doesn't exist).

**Green — make it pass:** add the `/quiz-page` route to `server/main.py`; create `web/quiz.html` and
`web/js/quiz.js`; add the nav link to every page. (The interactive answer-highlighting is verified by
hand via `python app.py --browser`; the route test guards the wiring.)

**Why it matters:** This is the artifact the user actually touches; wiring it like the existing pages
keeps the app consistent and the route test stops the page silently 404-ing after a rename.

**Gate:** `test_quiz_page_served` passes and `python app.py --browser` shows a working quiz round-trip.
**Faithfulness:** point the route at a non-existent file → the test goes red.

**Commit:** `feat(web): add quiz page (reading/meaning/cloze)`

---

## Phase 6 — Polish (optional but recommended)

### Step 6.1 — Mixed-mode + difficulty via priority tags

**Goal:** A `type=mixed` that randomly picks among the three, and distractors weighted by JMdict
priority tags so decoys are plausibly common words rather than rare ones.

**What we're building (read this first).** Two refinements: `make_question(kind="mixed", …)` chooses a
generator at random per call; and `pick_distractors` can prefer pool words of similar commonness using
JMdict's `news1/ichi1/nfXX` priority tags (exposed by jamdict) as a difficulty proxy — closer to true
JLPT-level matching without an external word list.

**Red — write the test:**
- `test_mixed_returns_valid_kind` *(invariant)*: many `Random(seed)` draws all yield a valid `kind`
  and a 4-choice question.
- `test_distractors_prefer_similar_frequency` *(invariant)*: given a frequency field on `VocabEntry`,
  distractors skew toward the target's band.
- Run → **red**.

**Green — make it pass:** add the `mixed` dispatcher and an optional frequency weight to
`pick_distractors`; populate frequency from JMdict priority tags in the API pool builder.

**Why it matters:** Plausible, level-matched distractors are what separate a real quiz from a giveaway.

**Gate:** the polish tests pass. **Faithfulness:** ignore the frequency band (uniform pick) →
`test_distractors_prefer_similar_frequency` goes red.

**Commit:** `feat(quiz): add mixed mode + frequency-weighted distractors`

---

## Key data & helpers (one place to look them up)

| Topic | Definition |
|---|---|
| **`VocabEntry`** | `(lemma, reading, meaning, pos)` — DB-free unit the pure layer uses |
| **`Question`** | `(kind, prompt, choices: tuple, answer_index, context_html=None, target_lemma="")` |
| **Choice count** | 1 correct + 3 distractors = 4, shuffled; `answer_index` records position |
| **RNG** | every generator takes `rng: random.Random`; tests pass `Random(0)`, API passes `Random()` |
| **Distractors** | exclude target; prefer same POS; top up from other POS; exactly `min(n, available)`; unique |
| **Sentence split** | split on `。！？\n`, keep terminator, drop blanks |
| **Blanking** | match token by `dictionary_form()==lemma`, replace its **surface** with `____` |
| **Grading** | `grade(q, i) == (i == q.answer_index)`; out-of-range ⇒ `False` |
| **Cross-request** | `_pending: dict[str, Question]` in-process; `/quiz/next` mints uuid, `/quiz/answer` looks up |
| **FSRS map (opt)** | wrong ⇒ `Rating.Again(1)`, right ⇒ `Rating.Good(3)` |

---

## Quiz concept → Python component map

| Concept | Python home |
|---|---|
| Vocab unit, question, grading | `server/quiz.py` (`VocabEntry`, `Question`, `grade`) |
| Distractor selection | `server/quiz.py` (`pick_distractors`) |
| Reading / meaning / cloze generators | `server/quiz.py` (`make_*_question`) |
| Sentence split + blanking | `server/quiz.py` (`split_sentences`, `blank_target`) |
| Dictionary glosses | reuse `server/dictionary.py` (`lookup_meanings`) |
| Furigana for cloze context | reuse `server/render.py` (`render_ruby`) |
| `/quiz/next`, `/quiz/answer`, `/quiz-page` | `server/main.py` |
| UI | `web/quiz.html`, `web/js/quiz.js`, nav link in all pages |
| Tests | `tests/test_quiz.py` (pure), `tests/test_api.py` (endpoints) |

---

## Suggested file layout

Tests are first-class: each test is written **before** the code it checks.

```
japanese-learning-app/
├── server/
│   ├── quiz.py                  # NEW — pure quiz logic (Phases 1–3)
│   ├── main.py                  # +/quiz/next, /quiz/answer, /quiz-page (Phase 4–5)
│   ├── dictionary.py            # reused (lookup_meanings)
│   └── render.py                # reused (render_ruby for cloze context)
├── web/
│   ├── quiz.html                # NEW (Phase 5)
│   ├── js/quiz.js               # NEW (Phase 5)
│   └── {index,import,vocab,review,stats}.html  # +Quiz nav link
├── tests/
│   ├── test_quiz.py             # NEW — pure-logic tests (Phases 0.2–3)
│   ├── test_api.py              # +quiz endpoint tests (Phase 4–5)
│   └── conftest.py              # reused fixtures: tokenizer, dictionary, db
└── doc/
    └── adr-002-quiz-engine.md   # NEW (Step 0.3)
```

---

## Milestone checklist (tape this above your desk)

Each box flips only when its step's test was written first, seen to fail, is now green — *and you've
sabotaged the code to confirm the test can fail.*

- [ ] **Phase 0** — `pytest -q` green baseline; deterministic pool/RNG helpers meta-tested; ADR written
- [ ] **Phase 1** — `pick_distractors`: excludes target, same-POS preference, fallback, deterministic
- [ ] **Phase 2** — reading golden (`猫`→`ねこ`); meaning distractors from *other* words; sentence split + lemma-aware blank; cloze `"猫が____を食べた。"`
- [ ] **Phase 3** — `grade` correct/incorrect/out-of-range
- [ ] **Phase 4** — `/quiz/next` shape (no `answer_index`) + 400 on tiny pool; `/quiz/answer` round-trip + 404; (opt) FSRS log
- [ ] **Phase 5** — `/quiz-page` served and wired; working round-trip in `--browser`
- [ ] **Phase 6** — mixed mode; frequency-weighted distractors

---

I can scaffold `server/quiz.py` + the `tests/test_quiz.py` Red tests for Phase 1 whenever you want to
begin — that's the natural first commit.
