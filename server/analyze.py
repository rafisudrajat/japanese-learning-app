from dataclasses import dataclass

import jaconv
from jamdict import Jamdict
from sudachipy.tokenizer import Tokenizer

from server.dictionary import lookup_meanings


@dataclass(frozen=True)
class RawToken:
    surface: str
    lemma: str
    reading_katakana: str
    pos: tuple[str, ...]


@dataclass(frozen=True)
class Token:
    surface: str
    reading_hiragana: str
    lemma: str
    meanings: list[str]
    pos: tuple[str, ...]
    known: bool


def to_hiragana(reading_katakana: str) -> str:
    return jaconv.kata2hira(reading_katakana)


def tokenize(text: str, tokenizer: Tokenizer) -> list[RawToken]:
    return [
        RawToken(
            surface=m.surface(),
            lemma=m.dictionary_form(),
            reading_katakana=m.reading_form(),
            pos=tuple(m.part_of_speech()),
        )
        for m in tokenizer.tokenize(text)
    ]


def analyze(
    text: str,
    tokenizer: Tokenizer,
    dictionary: Jamdict,
    known_lemmas: set[str] | None = None,
) -> list[Token]:
    _known = known_lemmas or set()
    return [
        Token(
            surface=raw.surface,
            reading_hiragana=to_hiragana(raw.reading_katakana),
            lemma=raw.lemma,
            meanings=lookup_meanings(raw.lemma, dictionary),
            pos=raw.pos,
            known=raw.lemma in _known,
        )
        for raw in tokenize(text, tokenizer)
    ]


class CachedAnalyzer:
    def __init__(self, tokenizer: Tokenizer, dictionary: Jamdict) -> None:
        self._tokenizer = tokenizer
        self._dictionary = dictionary
        self._cache: dict[str, list[Token]] = {}
        self.tokenize_calls: int = 0

    def __call__(self, text: str) -> list[Token]:
        if text in self._cache:
            return self._cache[text]
        self.tokenize_calls += 1
        result = analyze(text, self._tokenizer, self._dictionary)
        self._cache[text] = result
        return result
