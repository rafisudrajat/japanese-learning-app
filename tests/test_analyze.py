from sudachipy.tokenizer import Tokenizer

from server.analyze import RawToken, to_hiragana, tokenize


def test_tokenize_lemma_and_reading(tokenizer: Tokenizer) -> None:
    tokens: list[RawToken] = tokenize("本を読んだ", tokenizer)
    verb = next(t for t in tokens if t.surface == "読ん")
    assert verb.lemma == "読む"
    assert verb.reading_katakana == "ヨン"
    noun = next(t for t in tokens if t.surface == "本")
    assert noun.lemma == "本"


def test_tokenize_is_pure(tokenizer: Tokenizer) -> None:
    tokens_a: list[RawToken] = tokenize("本を読んだ", tokenizer)
    tokens_b: list[RawToken] = tokenize("本を読んだ", tokenizer)
    assert tokens_a == tokens_b


def test_kata_to_hira() -> None:
    assert to_hiragana("タベル") == "たべる"


def test_kata_to_hira_idempotent() -> None:
    for x in ("タベル", "ねこ"):
        assert to_hiragana(to_hiragana(x)) == to_hiragana(x)
