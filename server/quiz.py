"""Pure quiz logic — no DB, no jamdict, no HTTP.

The API layer in ``server/main.py`` reads the database and feeds plain
``VocabEntry`` rows into these functions. Anything that makes a random choice
takes an injected ``random.Random`` so questions are reproducible under a seed
(never call the global ``random`` module here).
"""

import re
import random
from dataclasses import dataclass

from sudachipy.tokenizer import Tokenizer

from server.render import _contains_kanji


@dataclass(frozen=True)
class VocabEntry:
    """A single vocabulary row, decoupled from the SQLite schema."""

    lemma: str
    reading: str
    meaning: str
    pos: str
    frequency: int = 0


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
    when too few same-POS words exist. When the target has a nonzero frequency,
    same-POS candidates are sorted by frequency proximity before selection.
    Returns ``min(n, available)`` distinct entries — never the target, no
    duplicates — deterministically for a given RNG.
    """
    candidates = [e for e in pool if e.lemma != target.lemma]

    if same_pos:
        same = [e for e in candidates if e.pos == target.pos]
        other = [e for e in candidates if e.pos != target.pos]
    else:
        same, other = candidates, []

    if target.frequency > 0 and any(e.frequency > 0 for e in same):
        rng.shuffle(same)
        same.sort(key=lambda e: abs(e.frequency - target.frequency))
    else:
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


def make_meaning_question(
    target: VocabEntry, pool: list[VocabEntry], rng: random.Random
) -> Question:
    distractors = pick_distractors(target, pool, 3, rng)
    distractor_meanings = [d.meaning for d in distractors if d.meaning != target.meaning]
    while len(distractor_meanings) < 3 and len(distractor_meanings) < len(
        [e for e in pool if e.lemma != target.lemma and e.meaning != target.meaning]
    ):
        extra = pick_distractors(target, pool, 3, rng)
        for d in extra:
            if d.meaning != target.meaning and d.meaning not in distractor_meanings:
                distractor_meanings.append(d.meaning)
                if len(distractor_meanings) == 3:
                    break
    choices = distractor_meanings[:3]
    pos = rng.randrange(len(choices) + 1)
    choices.insert(pos, target.meaning)
    return Question(
        kind="meaning",
        prompt=target.lemma,
        choices=tuple(choices),
        answer_index=pos,
        target_lemma=target.lemma,
    )


_SENTENCE_RE = re.compile(r"[^。！？\n]*[。！？\n]")


def split_sentences(text: str) -> list[str]:
    return [m.group() for m in _SENTENCE_RE.finditer(text) if m.group().strip()]


def blank_target(sentence: str, target_lemma: str, tokenizer: Tokenizer) -> tuple[str, str]:
    for morpheme in tokenizer.tokenize(sentence):
        if morpheme.dictionary_form() == target_lemma:
            surface = morpheme.surface()
            start = morpheme.begin()
            end = morpheme.end()
            blanked = sentence[:start] + "____" + sentence[end:]
            return blanked, surface
    raise ValueError(f"lemma {target_lemma!r} not found in sentence")


def make_cloze_question(
    target: VocabEntry,
    sentence: str,
    pool: list[VocabEntry],
    tokenizer: Tokenizer,
    rng: random.Random,
) -> Question:
    blanked, removed_surface = blank_target(sentence, target.lemma, tokenizer)
    correct = removed_surface if removed_surface != target.lemma else target.lemma
    distractors = pick_distractors(target, pool, 3, rng)
    choices = [d.lemma for d in distractors]
    pos = rng.randrange(len(choices) + 1)
    choices.insert(pos, correct)
    return Question(
        kind="cloze",
        prompt=blanked,
        choices=tuple(choices),
        answer_index=pos,
        target_lemma=target.lemma,
    )


def make_mixed_question(
    pool: list[VocabEntry],
    rng: random.Random,
    sentence: str | None = None,
    tokenizer: Tokenizer | None = None,
) -> Question:
    kanji_targets = [e for e in pool if _contains_kanji(e.lemma)]
    generators: list[str] = ["meaning"]
    if len(kanji_targets) >= 4:
        generators.append("reading")
    if sentence is not None and tokenizer is not None:
        generators.append("cloze")
    kind = rng.choice(generators)
    if kind == "reading":
        target = rng.choice(kanji_targets)
        return make_reading_question(target, pool, rng)
    elif kind == "cloze" and sentence is not None and tokenizer is not None:
        target = rng.choice(pool)
        return make_cloze_question(target, sentence, pool, tokenizer, rng)
    else:
        target = rng.choice(pool)
        return make_meaning_question(target, pool, rng)


def grade(question: Question, choice_index: int) -> bool:
    return 0 <= choice_index < len(question.choices) and choice_index == question.answer_index
