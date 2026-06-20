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


def analyze(text: str, tokenizer: Tokenizer, dictionary: Jamdict) -> list[Token]:
    return [
        Token(
            surface=raw.surface,
            reading_hiragana=to_hiragana(raw.reading_katakana),
            lemma=raw.lemma,
            meanings=lookup_meanings(raw.lemma, dictionary),
            pos=raw.pos,
            known=False,
        )
        for raw in tokenize(text, tokenizer)
    ]
