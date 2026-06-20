"""Pure quiz logic — no DB, no jamdict, no HTTP.

The API layer in ``server/main.py`` reads the database and feeds plain
``VocabEntry`` rows into these functions. Anything that makes a random choice
takes an injected ``random.Random`` so questions are reproducible under a seed
(never call the global ``random`` module here).
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class VocabEntry:
    """A single vocabulary row, decoupled from the SQLite schema."""

    lemma: str
    reading: str
    meaning: str
    pos: str


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
