from jamdict import Jamdict
from sudachipy.tokenizer import Tokenizer

from server.analyze import CachedAnalyzer, RawToken, Token, analyze, to_hiragana, tokenize


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


def test_analyze_full_token(tokenizer: Tokenizer, dictionary: Jamdict) -> None:
    tokens: list[Token] = analyze("猫を見た", tokenizer, dictionary)
    verb = next(t for t in tokens if t.surface == "見")
    assert verb.lemma == "見る"
    assert verb.reading_hiragana == "み"
    assert all(c < "゠" or c > "ヿ" for c in verb.reading_hiragana)
    cat = next(t for t in tokens if t.surface == "猫")
    assert any("cat" in m.lower() for m in cat.meanings)


def test_lemma_reading_uses_dictionary_form(tokenizer: Tokenizer, dictionary: Jamdict) -> None:
    # Inflected verb: the surface 焼け reads やけ, but the dictionary form 焼ける reads やける.
    # reading_hiragana stays surface (for furigana); lemma_reading_hiragana is the dict form.
    tokens: list[Token] = analyze("魚が焼けた", tokenizer, dictionary)
    verb = next(t for t in tokens if t.lemma == "焼ける")
    assert verb.reading_hiragana == "やけ"
    assert verb.lemma_reading_hiragana == "やける"


def test_lemma_reading_matches_for_uninflected_words(
    tokenizer: Tokenizer, dictionary: Jamdict
) -> None:
    tokens: list[Token] = analyze("猫", tokenizer, dictionary)
    cat = next(t for t in tokens if t.lemma == "猫")
    assert cat.reading_hiragana == "ねこ"
    assert cat.lemma_reading_hiragana == "ねこ"


def test_analyze_emits_all_fields(tokenizer: Tokenizer, dictionary: Jamdict) -> None:
    tokens: list[Token] = analyze("猫を見た", tokenizer, dictionary)
    for t in tokens:
        assert isinstance(t.surface, str) and t.surface
        assert isinstance(t.reading_hiragana, str) and t.reading_hiragana
        assert isinstance(t.lemma, str) and t.lemma
        assert isinstance(t.meanings, list)
        assert isinstance(t.pos, tuple) and len(t.pos) > 0
        assert t.known is False


def test_cache_returns_equal_result(tokenizer: Tokenizer, dictionary: Jamdict) -> None:
    cached = CachedAnalyzer(tokenizer, dictionary)
    text = "猫を見た"
    cached(text)
    assert cached(text) == analyze(text, tokenizer, dictionary)


def test_cache_hits_skip_tokenizer(tokenizer: Tokenizer, dictionary: Jamdict) -> None:
    cached = CachedAnalyzer(tokenizer, dictionary)
    text = "猫を見た"
    cached(text)
    assert cached.tokenize_calls == 1
    cached(text)
    assert cached.tokenize_calls == 1


def test_known_flag_set_from_vocab(tokenizer: Tokenizer, dictionary: Jamdict) -> None:
    tokens: list[Token] = analyze("猫を見た", tokenizer, dictionary, known_lemmas={"猫"})
    cat = next(t for t in tokens if t.surface == "猫")
    assert cat.known is True
    verb = next(t for t in tokens if t.lemma == "見る")
    assert verb.known is False
