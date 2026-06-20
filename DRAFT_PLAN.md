# Japanese Reader + SRS App — Implementation Roadmap

A local-first desktop app (Windows + Linux, Python) that lets you:

- Import Japanese **news or stories** by pasting text, fetching a URL, or reading inside an in-app browser.
- Read the text with **furigana** (kana over kanji) and **click any word** to see its reading and English meaning.
- **Auto-collect new vocabulary** from what you read (deduplicated against words you already know).
- **Review vocabulary** with a modern spaced-repetition algorithm (FSRS), Anki-style.

Everything in the stack is free and either permissively licensed or fine for private use.

---

## 1. Key decisions (read this first)

These three choices shape everything else.

**Don't reuse Anki's code — use the FSRS algorithm as a standalone library.**
Anki is licensed under AGPL-3.0. For private use that's harmless, but the moment you ever distribute the app, AGPL would force your *entire* codebase to be AGPL too. You don't need to take that on: the valuable part — Anki's modern scheduler — is published separately as the MIT-licensed `fsrs` package (`py-fsrs`). Modern Anki no longer uses the old SM-2 algorithm; it uses **FSRS** (Free Spaced Repetition Scheduler), which models memory more directly and needs fewer reviews for the same retention. So: `pip install fsrs`, skip Anki's repo entirely. *(Optional later: export `.apkg` files via `genanki` so you can review on your phone in real Anki.)*

**Render the UI as HTML in a webview — because of furigana.**
Furigana is HTML's native `<ruby>`/`<rt>` feature and is painful to render in a pure desktop-widget toolkit. So the app is a Python "engine" (all language logic + database) behind a thin local HTTP API, with an HTML/CSS/JS front end shown in a native window via **pywebview**. Bonus: keeping a clean HTTP boundary means you can later run it as a pure web app on a home server with zero rewrite. It also gives you the in-app browser you need for importing hostile sites (see §6).

**Treat "fetch the text" as a pluggable layer with a guaranteed fallback.**
Fetching varies enormously by site. Some sites (e.g. Yahoo News Japan) block bots via `robots.txt`, render with JavaScript, and expire articles within weeks. Others (most blogs, Aozora Bunko) are trivial. So the importer has tiers (§6), and a **paste-text** option that always works.

---

## 2. Tech stack

| Concern | Library | License | Notes |
|---|---|---|---|
| Tokenize + readings | **SudachiPy** + `SudachiDict-core` | Apache-2.0 | Tokens align with dictionary entries; split modes A/B/C help learners. |
| (alt tokenizer) | `fugashi` + `unidic-lite` | MIT | Faster; good readings. |
| (fallback tokenizer) | `janome` | Apache-2.0 | Pure Python, zero compilation; slowest. |
| Word → English | **jamdict** (bundles JMdict + KanjiDic) | MIT lib | JMdict data is CC BY-SA — attribution only matters if you distribute. |
| Kana conversion | **jaconv** | MIT | `kata2hira()` converts Sudachi's katakana readings to hiragana. |
| Spaced repetition | **fsrs** (`py-fsrs`) | MIT | Modern algorithm, no Anki coupling. |
| Article extraction | **trafilatura** | Apache-2.0 | Top-ranked main-text extractor; strips nav/ads/boilerplate. |
| Storage | **SQLite** (`sqlite3` or SQLModel) | builtin / MIT | Single-file, local-first. |
| Backend API | **FastAPI** + `uvicorn` | MIT | Bind to `127.0.0.1` only. |
| Desktop shell | **pywebview** | BSD | Native window around a system webview. |
| (tier-3 fetch, optional) | **playwright** | Apache-2.0 | Headless browser for JS-heavy sites. |
| Packaging | **PyInstaller** | GPL-with-exception (output is yours) | Builds Windows `.exe` and Linux binaries. |
| Anki export (optional) | **genanki** | MIT | Generate `.apkg` for review in real Anki. |

Install (core):
```bash
pip install sudachipy sudachidict_core jamdict jamdict-data jaconv fsrs \
            trafilatura fastapi uvicorn pywebview
# optional extras
pip install playwright genanki && playwright install chromium
```

---

## 3. Architecture

Local client-server. The Python engine owns all language work and the database; the front end is HTML in a native window.

```
┌─────────────────────────────────────────────────────────┐
│  Desktop window (pywebview)                               │
│  ┌─────────────────────────────────────────────────┐     │
│  │  Front end: HTML + CSS + a little JS              │     │
│  │   • Reader view   (text with <ruby> furigana)     │     │
│  │   • Word popover  (reading, meaning, save button) │     │
│  │   • Import view   (paste / URL / in-app browser)  │     │
│  │   • Triage view   (confirm new vocab candidates)  │     │
│  │   • Review view   (FSRS flashcards)               │     │
│  └───────────────────────┬─────────────────────────┘     │
└──────────────────────────┼──────────────────────────────┘
                           │  HTTP (localhost only)
┌──────────────────────────┼──────────────────────────────┐
│  Python backend (FastAPI)                                 │
│                                                           │
│   /analyze     /import     /vocab     /review/*    /export│
│       │           │           │           │           │   │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │Tokenizer│ │ Importer │ │Dictionary│ │Scheduler │       │
│  │SudachiPy│ │trafilatura│ │ jamdict │ │  fsrs    │       │
│  └─────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                          │                                │
│                   ┌──────▼───────┐                        │
│                   │  SQLite DB    │                        │
│                   └──────────────┘                        │
└───────────────────────────────────────────────────────────┘
```

Suggested project layout:
```
japanese_reader/
  app.py                 # pywebview launcher: starts FastAPI, opens window
  server/
    main.py              # FastAPI app + routes
    analyze.py           # analyze(text) -> list[Token]
    importer/
      sources.py         # PasteSource, UrlSource, BrowserSource (strategy)
      extract.py         # trafilatura wrapper + encoding detection
      vocab_intake.py    # POS filter, lemma dedupe, lookup, frequency
    dictionary.py        # jamdict lookups (lemma -> meanings)
    scheduler.py         # fsrs wrapper (review_card, persistence)
    db.py                # SQLite schema + queries
  web/                   # front end
    index.html
    reader.js  review.js  import.js
    style.css
  data/                  # app database lives here at runtime
  tests/
  pyproject.toml
```

---

## 4. Data model (SQLite)

Keep linguistic content (`vocab`) separate from scheduling state (`cards`) — they evolve independently.

```sql
CREATE TABLE texts (
  id          INTEGER PRIMARY KEY,
  title       TEXT,
  source_type TEXT,          -- 'paste' | 'url' | 'browser'
  source_url  TEXT,          -- nullable
  raw_text    TEXT NOT NULL,
  analysis    TEXT,          -- cached analyzed tokens as JSON
  created_at  TEXT NOT NULL
);

CREATE TABLE vocab (
  id              INTEGER PRIMARY KEY,
  lemma           TEXT NOT NULL UNIQUE,   -- dictionary form, the dedupe key
  reading         TEXT,                   -- hiragana
  primary_meaning TEXT,
  pos             TEXT,
  status          TEXT NOT NULL DEFAULT 'new',  -- 'new'|'learning'|'known'
  seen_count      INTEGER NOT NULL DEFAULT 0,   -- total occurrences seen
  text_count      INTEGER NOT NULL DEFAULT 0,   -- # of distinct texts
  first_seen_text_id INTEGER REFERENCES texts(id),
  created_at      TEXT NOT NULL
);

CREATE TABLE cards (
  id         INTEGER PRIMARY KEY,
  vocab_id   INTEGER NOT NULL REFERENCES vocab(id),
  -- FSRS-owned fields (persist exactly what the fsrs Card object holds):
  state      INTEGER,        -- New/Learning/Review/Relearning
  due        TEXT,
  stability  REAL,
  difficulty REAL,
  last_review TEXT,
  reps       INTEGER DEFAULT 0,
  lapses     INTEGER DEFAULT 0
);

CREATE TABLE review_logs (   -- keep from day one; needed to optimize FSRS later
  id          INTEGER PRIMARY KEY,
  card_id     INTEGER NOT NULL REFERENCES cards(id),
  rating      INTEGER NOT NULL,   -- 1 Again, 2 Hard, 3 Good, 4 Easy
  reviewed_at TEXT NOT NULL
);
```

`lemma UNIQUE` is what makes "don't re-collect words I have" work: 食べた / 食べます / 食べる all map to one row keyed on the dictionary form 食べる.

---

## 5. The analysis pipeline (the heart of the reader)

For one chunk of text, `analyze(text)` does:

1. Tokenize with SudachiPy → morphemes.
2. For each morpheme, pull: **surface** (as written), **dictionary form** (lemma), **reading** (katakana), **part of speech**.
3. Convert reading to hiragana with `jaconv.kata2hira(...)`.
4. Look up the **dictionary form** in jamdict → English meanings.
5. Emit a display token: `{surface, reading_hiragana, lemma, meanings[], pos, known: bool}`.

`known` is set by checking the lemma against `vocab` where `status='known'`, so already-mastered words can be styled differently (or skipped for furigana).

**Furigana rendering.** Each token becomes `<ruby>surface<rt>reading</rt></ruby>`.

> **Known wrinkle — furigana alignment.** SudachiPy gives the reading of the *whole token*. The naive version puts the whole reading over the whole word: fine for pure-kanji words (都庁→とちょう), slightly ugly for mixed words (食べる shown as 食べる(たべる) instead of 食(た)べる). Build the naive version first — it's *correct*, just not pretty — and add per-kanji alignment later as a self-contained polish task. Don't block on it.

---

## 6. The import feature (3 tiers + auto-vocab)

### Fetch tiers — build in this order

**Tier 1 — Paste raw text.** A text box you drop article text into. Works for *any* source, including bot-blocked sites (you select-all → copy → paste). Bulletproof baseline; build it first.

**Tier 2 — Fetch URL + extract.** Download the page, run it through **trafilatura** to strip nav/ads/boilerplate and return clean article text. Handles the majority of friendly sites (most blogs, Aozora Bunko, simpler news). Detect/convert encoding on the way in — many Aozora files are **Shift-JIS**, not UTF-8.

**Tier 3 — Render in a real browser, then extract.** For JS-heavy or bot-blocking sites:
- *User-driven (recommended):* add an in-app browser tab. You navigate to the article like a normal reader, then hit **"Import this page"** to grab text from the already-rendered DOM. The JavaScript has already run, and there's no bot impersonating a human — it *is* a human in a real browser, like Safari/Firefox Reader Mode. This is the approach for hard sites.
- *Headless (optional):* Playwright drives a hidden Chromium. Automated, but goes around `robots.txt` — use sparingly and slowly.

**Etiquette / legal note (not legal advice):** the clean line is "automated bulk harvesting" (avoid) vs. "a person reading one article into their own reader" (fine — effectively Reader Mode). Keep requests slow, never redistribute fetched text, respect `robots.txt` where you reasonably can. Tiers 1 and 3-user-driven keep you on the comfortable side.

### Recommended sources

- **Aozora Bunko** — large library of public-domain Japanese literature; clean text, no bot-blocking. Best for the "story" use case. (Watch for Shift-JIS encoding.)
- **Watanoc** — free "Easy Japanese" news/reading with furigana, aimed at N3–N5 learners.
- **Regular NHK News** and most ordinary blogs — work with Tier 2.
- **Avoid NHK News Web Easy** — as of 2025 it was renamed and locked behind an NHK subscription contract, so it's no longer freely usable.
- **Avoid Yahoo News Japan as a fetch target** — bot-blocked, JS-rendered, articles expire. Use Tier 1 or Tier 3-user-driven if you want a specific Yahoo article.

### Auto-vocabulary pipeline

Once any tier hands you clean text: **analyze → filter to content words → dedupe by lemma → triage → collect.**

1. Run the text through `analyze()`.
2. **POS filter:** keep nouns, verbs, adjectives, adverbs; drop particles, auxiliaries, punctuation, bare numbers. (SudachiPy's POS tags make this a simple rule.)
3. **Dedupe by lemma** against existing `vocab`. Anything already present (any status) is not "new."
4. Remaining lemmas are **new candidates**; attach meanings via jamdict.
5. **Triage, don't dump.** A single news article can yield ~40 new words, many you half-know. Route candidates into a **triage screen**: tap *Keep* (creates an FSRS card, status→`learning`) or *Already know* (status→`known`, never resurfaces). This grows a "known words" set so future imports surface fewer, genuinely-new words.
6. **Frequency:** increment `seen_count` / `text_count` so the triage list can be frequency-sorted — learn the highest-value words first.

---

## 7. Phased roadmap

Each phase ends with something usable. Riskiest unknowns come first.

### Phase 0 — Spike (2–3 days)
Prove the unpredictable pieces in a throwaway script:
- Tokenize a real Japanese sentence with SudachiPy; print surface + dictionary form + hiragana reading.
- Look those lemmas up in jamdict; print meanings.
- **Done when:** it works end-to-end on messy real text. The project is now de-risked. Decide SudachiPy vs. fugashi here.

### Phase 1 — Analysis engine (week 1)
- Wrap the spike into `analyze(text) -> list[Token]`.
- Cache results so reopening a text doesn't re-tokenize.
- `pytest` over sentences with verbs, particles, katakana.
- **Deliverable:** tested function turning raw Japanese into annotated tokens.

### Phase 2 — Reader UI (week 2)
- FastAPI with `/analyze`; wrap in a pywebview window.
- Render the reader: text with hiragana furigana via `<ruby>`; click/hover popover with reading + meanings.
- **Deliverable:** paste an article, read with furigana, tap-to-translate. Already useful.

### Phase 3 — Vocabulary storage (week 3)
- Add SQLite + `texts`/`vocab` tables.
- "Save word" button on the popover; vocab-list screen with search/filter.
- Mark already-saved words visually in the reader.
- **Deliverable:** a growing personal word list, deduped by lemma.

### Phase 4 — Import + auto-vocab (weeks 4–5)  ← the feature you asked for
- **4a.** Tier-1 paste intake → reuse `analyze()`.
- **4b.** `vocab_intake.py`: POS filter, lemma dedupe, jamdict lookup, frequency counting. *(Source-agnostic — works on pasted text before any scraping exists.)*
- **4c.** Triage screen: Keep / Already-know, frequency-sorted.
- **4d.** Tier-2 URL fetch with trafilatura + encoding detection, tested against Watanoc or Aozora.
- **4e.** Tier-3 in-app browser "Import this page" for hard sites.
- **Deliverable:** import news/stories from text, friendly URLs, or the in-app browser, and auto-build triaged vocab.

### Phase 5 — Spaced repetition (weeks 6–7)
- Add `fsrs` + `cards`/`review_logs` tables.
- Review screen: show word → reveal meaning → four buttons (Again/Hard/Good/Easy = 1–4).
- On each rating, call `scheduler.review_card(card, rating)`, persist returned card fields, log the review.
- **Deliverable:** real Anki-style study driven by FSRS.

### Phase 6 — Polish & packaging (week 8+)
Pick from:
- Per-kanji furigana alignment.
- FSRS parameter optimization on your own `review_logs` (re-optimize ~monthly once you have history).
- Stats dashboard (reviews/day, accuracy, retention).
- CSV import/export; `genanki` `.apkg` export for phone review.
- **Packaging:** PyInstaller for Windows + Linux. Watch bundle size — SudachiDict and the JMdict database are each tens of MB; confirm they ship as data files and are found at runtime.
- **Deliverable:** double-clickable app on both OSes.

**Timeline:** ~8 weeks at a relaxed pace, but Phases 0–2 (~2 weeks) already give a working reader, and Phase 4 delivers the import + auto-vocab feature.

---

## 8. Gotchas checklist

- [ ] Look up and store the **dictionary form (lemma)**, not the surface form — this is what makes dedupe and "don't re-collect" work.
- [ ] Convert Sudachi's **katakana** readings to **hiragana** (`jaconv.kata2hira`).
- [ ] Handle **Shift-JIS** encoding on import (esp. Aozora Bunko).
- [ ] Bind FastAPI to **127.0.0.1** only — it's a local app, not a public server.
- [ ] Keep **`review_logs`** from day one, even before you use them.
- [ ] Naive whole-word furigana first; **per-kanji alignment is a later polish task**.
- [ ] Triage new vocab into an inbox; **don't auto-dump** everything into the review deck.
- [ ] Ship the dictionaries as **bundled data files** when packaging; verify runtime paths.
- [ ] If you ever distribute: JMdict is CC BY-SA (add attribution); avoid Anki source (AGPL); prefer `fsrs`/`genanki` (MIT).