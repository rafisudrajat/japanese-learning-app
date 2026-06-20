from dataclasses import dataclass

import jaconv
from sudachipy.tokenizer import Tokenizer


@dataclass(frozen=True)
class RawToken:
    surface: str
    lemma: str
    reading_katakana: str
    pos: tuple[str, ...]


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
