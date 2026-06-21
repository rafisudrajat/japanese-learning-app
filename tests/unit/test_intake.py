import sqlite3

from server.analyze import analyze
from server.db import upsert_vocab
from server.importer.vocab_intake import (
    collect_candidates,
    is_content_word,
    is_japanese_word,
)


def test_keeps_content_drops_particles(tokenizer, dictionary, db: sqlite3.Connection) -> None:
    tokens = analyze("猫が魚を食べた", tokenizer, dictionary)
    content = [t for t in tokens if is_content_word(t.pos)]
    content_lemmas = {t.lemma for t in content}
    assert "猫" in content_lemmas
    assert "魚" in content_lemmas
    assert "食べる" in content_lemmas
    dropped_lemmas = {t.lemma for t in tokens if not is_content_word(t.pos)}
    assert "が" in dropped_lemmas
    assert "を" in dropped_lemmas


def test_drops_numbers_and_punct(tokenizer, dictionary) -> None:
    tokens = analyze("100。", tokenizer, dictionary)
    for t in tokens:
        assert not is_content_word(t.pos), f"{t.surface} ({t.pos}) should not be content"


def test_drops_proper_nouns() -> None:
    # Proper nouns (names, places, organizations) are not general vocabulary.
    assert not is_content_word(("名詞", "固有名詞", "一般"))
    assert not is_content_word(("名詞", "固有名詞", "人名", "一般"))
    assert not is_content_word(("名詞", "固有名詞", "地名", "国"))
    # Common nouns are still kept.
    assert is_content_word(("名詞", "普通名詞", "一般"))


def test_is_japanese_word() -> None:
    # Real Japanese words contain kana or kanji.
    assert is_japanese_word("猫")  # kanji
    assert is_japanese_word("システム")  # katakana loanword
    assert is_japanese_word("たべる")  # hiragana
    # Latin script and symbols are not Japanese vocabulary.
    assert not is_japanese_word("%")
    assert not is_japanese_word("t")
    assert not is_japanese_word("FIFA")
    assert not is_japanese_word("horizon")


def test_drops_non_japanese_and_proper_nouns(tokenizer, dictionary, db: sqlite3.Connection) -> None:
    tokens = analyze("FIFAがモロッコでシステムを発表した", tokenizer, dictionary)
    candidates = collect_candidates(db, tokens)
    lemmas = {c.lemma for c in candidates}
    assert "FIFA" not in lemmas  # Latin-script + proper noun
    assert "モロッコ" not in lemmas  # proper noun (place name)
    assert "システム" in lemmas  # legitimate katakana loanword
    assert "発表" in lemmas  # legitimate kanji word


def test_excludes_known_vocab(tokenizer, dictionary, db: sqlite3.Connection) -> None:
    upsert_vocab(db, "食べる", "たべる", "動詞", now="2025-01-01")
    tokens = analyze("今日は寿司を食べた", tokenizer, dictionary)
    candidates = collect_candidates(db, tokens)
    candidate_lemmas = {c.lemma for c in candidates}
    assert "食べる" not in candidate_lemmas


def test_dedupes_and_counts_frequency(tokenizer, dictionary, db: sqlite3.Connection) -> None:
    tokens = analyze("猫と猫と猫", tokenizer, dictionary)
    candidates = collect_candidates(db, tokens)
    cat_candidates = [c for c in candidates if c.lemma == "猫"]
    assert len(cat_candidates) == 1
    assert cat_candidates[0].frequency == 3


def test_candidates_sorted_by_frequency(tokenizer, dictionary, db: sqlite3.Connection) -> None:
    tokens = analyze("猫と猫と猫と犬", tokenizer, dictionary)
    candidates = collect_candidates(db, tokens)
    content_candidates = [c for c in candidates if c.lemma in ("猫", "犬")]
    if len(content_candidates) >= 2:
        assert content_candidates[0].frequency >= content_candidates[1].frequency
