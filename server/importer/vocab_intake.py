import sqlite3
from collections import Counter
from dataclasses import dataclass

from server.analyze import Token


_CONTENT_POS = {"名詞", "動詞", "形容詞", "副詞"}
# Noun sub-categories that are not learnable vocabulary: bare numbers and
# proper nouns (person names, place names, organizations like FIFA / モロッコ).
_DROP_NOUN_SUB = {"数詞", "固有名詞"}


def is_content_word(pos: tuple[str, ...]) -> bool:
    if not pos:
        return False
    major = pos[0]
    if major in ("記号", "補助記号"):
        return False
    if major not in _CONTENT_POS:
        return False
    if major == "名詞" and len(pos) > 1 and pos[1] in _DROP_NOUN_SUB:
        return False
    return True


def _is_japanese_char(c: str) -> bool:
    return (
        "぀" <= c <= "ゟ"  # hiragana
        or "゠" <= c <= "ヿ"  # katakana
        or "一" <= c <= "鿿"  # CJK unified ideographs (kanji)
        or "㐀" <= c <= "䶿"  # CJK extension A
    )


def is_japanese_word(lemma: str) -> bool:
    """True if the word contains kana or kanji.

    Drops Latin-script tokens (``horizon``, ``FIFA``, ``t``) and symbols (``%``)
    that SudachiPy still tags as common nouns but are not Japanese vocabulary.
    """
    return any(_is_japanese_char(c) for c in lemma)


@dataclass
class Candidate:
    lemma: str
    reading: str
    meanings: list[str]
    pos: str
    frequency: int


def collect_candidates(conn: sqlite3.Connection, tokens: list[Token]) -> list[Candidate]:
    existing = {row[0] for row in conn.execute("SELECT lemma FROM vocab").fetchall()}

    counts: Counter[str] = Counter()
    token_by_lemma: dict[str, Token] = {}
    for t in tokens:
        if not is_content_word(t.pos):
            continue
        if not is_japanese_word(t.lemma):
            continue
        if t.lemma in existing:
            continue
        counts[t.lemma] += 1
        if t.lemma not in token_by_lemma:
            token_by_lemma[t.lemma] = t

    candidates = []
    for lemma, freq in counts.most_common():
        t = token_by_lemma[lemma]
        candidates.append(
            Candidate(
                lemma=lemma,
                reading=t.lemma_reading_hiragana or t.reading_hiragana,
                meanings=t.meanings,
                pos=t.pos[0] if t.pos else "",
                frequency=freq,
            )
        )
    return candidates
