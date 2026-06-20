import sqlite3
from collections import Counter
from dataclasses import dataclass

from server.analyze import Token


_CONTENT_POS = {"名詞", "動詞", "形容詞", "副詞"}
_DROP_NOUN_SUB = {"数詞"}


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
                reading=t.reading_hiragana,
                meanings=t.meanings,
                pos=t.pos[0] if t.pos else "",
                frequency=freq,
            )
        )
    return candidates
