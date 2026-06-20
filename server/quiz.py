"""Pure quiz logic — no DB, no jamdict, no HTTP.

The API layer in ``server/main.py`` reads the database and feeds plain
``VocabEntry`` rows into these functions. Anything that makes a random choice
takes an injected ``random.Random`` so questions are reproducible under a seed
(never call the global ``random`` module here).
"""

import random
from dataclasses import dataclass

from server.render import _contains_kanji


@dataclass(frozen=True)
class VocabEntry:
    """A single vocabulary row, decoupled from the SQLite schema."""

    lemma: str
    reading: str
    meaning: str
    pos: str


@dataclass(frozen=True)
class Question:
    kind: str
    prompt: str
    choices: tuple[str, ...]
    answer_index: int
    context_html: str | None = None
    target_lemma: str = ""


def sample_one(pool: list[VocabEntry], rng: random.Random) -> VocabEntry:
    """Pick one entry using the injected RNG (deterministic for a given seed)."""
    return rng.choice(pool)


def pick_distractors(
    target: VocabEntry,
    pool: list[VocabEntry],
    n: int,
    rng: random.Random,
    same_pos: bool = True,
) -> list[VocabEntry]:
    """Choose ``n`` plausible wrong options for a multiple-choice question.

    Excludes the target, prefers same-POS candidates, and tops up from the rest
    when too few same-POS words exist. Returns ``min(n, available)`` distinct
    entries — never the target, no duplicates — deterministically for a given RNG.
    """
    candidates = [e for e in pool if e.lemma != target.lemma]

    if same_pos:
        same = [e for e in candidates if e.pos == target.pos]
        other = [e for e in candidates if e.pos != target.pos]
    else:
        same, other = candidates, []

    rng.shuffle(same)
    rng.shuffle(other)
    ordered = same + other
    return ordered[:n]


def make_reading_question(
    target: VocabEntry, pool: list[VocabEntry], rng: random.Random
) -> Question:
    if not _contains_kanji(target.lemma):
        raise ValueError(f"target lemma {target.lemma!r} contains no kanji")
    distractors = pick_distractors(target, pool, 3, rng)
    choices = [d.reading for d in distractors]
    pos = rng.randrange(len(choices) + 1)
    choices.insert(pos, target.reading)
    return Question(
        kind="reading",
        prompt=target.lemma,
        choices=tuple(choices),
        answer_index=pos,
        target_lemma=target.lemma,
    )
