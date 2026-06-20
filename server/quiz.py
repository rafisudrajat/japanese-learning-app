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
