import random

import pytest

from server.quiz import (
    VocabEntry,
    blank_target,
    make_meaning_question,
    make_reading_question,
    pick_distractors,
    sample_one,
    split_sentences,
)


def make_pool(specs: list[tuple[str, str, str, str]]) -> list[VocabEntry]:
    """Turn terse (lemma, reading, meaning, pos) tuples into VocabEntry rows."""
    return [VocabEntry(*spec) for spec in specs]


def test_make_pool_shape() -> None:
    pool = make_pool([("猫", "ねこ", "cat", "名詞")])
    assert len(pool) == 1
    entry = pool[0]
    assert (entry.lemma, entry.reading, entry.meaning, entry.pos) == (
        "猫",
        "ねこ",
        "cat",
        "名詞",
    )


def test_seeded_rng_is_reproducible() -> None:
    pool = make_pool(
        [
            ("猫", "ねこ", "cat", "名詞"),
            ("犬", "いぬ", "dog", "名詞"),
            ("鳥", "とり", "bird", "名詞"),
            ("魚", "さかな", "fish", "名詞"),
            ("本", "ほん", "book", "名詞"),
        ]
    )

    def draw(seed: int) -> list[VocabEntry]:
        rng = random.Random(seed)
        return [sample_one(pool, rng) for _ in range(5)]

    # Same seed → identical sequence (the property every later golden test leans on).
    assert draw(0) == draw(0)
    # Different seed → different sequence.
    assert draw(0) != draw(1)


NOUN_POOL = [
    ("猫", "ねこ", "cat", "名詞"),
    ("犬", "いぬ", "dog", "名詞"),
    ("鳥", "とり", "bird", "名詞"),
    ("魚", "さかな", "fish", "名詞"),
    ("本", "ほん", "book", "名詞"),
]


def test_distractors_exclude_target() -> None:
    pool = make_pool(NOUN_POOL)
    target = pool[0]  # 猫
    distractors = pick_distractors(target, pool, 3, random.Random(0))
    assert len(distractors) == 3
    assert all(d.lemma != target.lemma for d in distractors)
    assert len({d.lemma for d in distractors}) == 3


def test_distractors_prefer_same_pos() -> None:
    pool = make_pool(
        [
            ("猫", "ねこ", "cat", "名詞"),
            ("犬", "いぬ", "dog", "名詞"),
            ("鳥", "とり", "bird", "名詞"),
            ("魚", "さかな", "fish", "名詞"),
            ("走る", "はしる", "to run", "動詞"),
            ("食べる", "たべる", "to eat", "動詞"),
            ("見る", "みる", "to see", "動詞"),
            ("飲む", "のむ", "to drink", "動詞"),
        ]
    )
    target = pool[0]  # 猫 (名詞)
    distractors = pick_distractors(target, pool, 3, random.Random(0))
    assert len(distractors) == 3
    assert all(d.pos == "名詞" for d in distractors)


def test_distractors_fallback_when_too_few_same_pos() -> None:
    pool = make_pool(
        [
            ("猫", "ねこ", "cat", "名詞"),
            ("犬", "いぬ", "dog", "名詞"),
            ("走る", "はしる", "to run", "動詞"),
            ("食べる", "たべる", "to eat", "動詞"),
            ("見る", "みる", "to see", "動詞"),
            ("飲む", "のむ", "to drink", "動詞"),
            ("寝る", "ねる", "to sleep", "動詞"),
        ]
    )
    target = pool[0]  # 猫 (名詞); only 1 other noun available
    distractors = pick_distractors(target, pool, 3, random.Random(0))
    assert len(distractors) == 3
    assert all(d.lemma != target.lemma for d in distractors)
    assert any(d.pos == "名詞" for d in distractors)
    assert any(d.pos == "動詞" for d in distractors)


def test_distractors_small_pool() -> None:
    pool = make_pool(NOUN_POOL[:3])  # 3 entries; minus the target ⇒ 2 usable
    target = pool[0]
    distractors = pick_distractors(target, pool, 3, random.Random(0))
    assert len(distractors) == 2
    assert len({d.lemma for d in distractors}) == 2
    assert all(d.lemma != target.lemma for d in distractors)


def test_distractors_deterministic() -> None:
    pool = make_pool(NOUN_POOL)
    target = pool[0]
    first = pick_distractors(target, pool, 3, random.Random(0))
    second = pick_distractors(target, pool, 3, random.Random(0))
    assert first == second


# ---------------------------------------------------------------------------
# Step 2.1 — Reading quiz (type A: 漢字読み)
# ---------------------------------------------------------------------------


def test_reading_question_golden() -> None:
    pool = make_pool(NOUN_POOL)
    target = pool[0]  # 猫 / ねこ / cat / 名詞
    q = make_reading_question(target, pool, random.Random(0))
    assert q.kind == "reading"
    assert q.prompt == "猫"
    assert "ねこ" in q.choices
    assert q.choices[q.answer_index] == "ねこ"
    assert q.target_lemma == "猫"


def test_reading_question_invariants() -> None:
    pool = make_pool(NOUN_POOL)
    target = pool[0]
    q = make_reading_question(target, pool, random.Random(0))
    assert len(q.choices) == 4
    assert len(set(q.choices)) == 4
    assert 0 <= q.answer_index < 4


def test_reading_question_rejects_kana_only() -> None:
    pool = make_pool(NOUN_POOL)
    kana_target = VocabEntry("ねこ", "ねこ", "cat", "名詞")
    with pytest.raises(ValueError):
        make_reading_question(kana_target, pool, random.Random(0))


# ---------------------------------------------------------------------------
# Step 2.2 — Meaning quiz (type B: recall)
# ---------------------------------------------------------------------------


def test_meaning_question_golden() -> None:
    pool = make_pool(NOUN_POOL)
    target = pool[0]  # 猫 / ねこ / cat / 名詞
    q = make_meaning_question(target, pool, random.Random(0))
    assert q.kind == "meaning"
    assert q.prompt == "猫"
    assert q.choices[q.answer_index] == "cat"
    assert q.target_lemma == "猫"


def test_meaning_distractors_are_other_words() -> None:
    pool = make_pool(NOUN_POOL)
    target = pool[0]  # cat
    q = make_meaning_question(target, pool, random.Random(0))
    meanings_of_others = {e.meaning for e in pool if e.lemma != target.lemma}
    for i, choice in enumerate(q.choices):
        if i != q.answer_index:
            assert choice in meanings_of_others
            assert choice != target.meaning


def test_meaning_question_invariants() -> None:
    pool = make_pool(NOUN_POOL)
    target = pool[0]
    q = make_meaning_question(target, pool, random.Random(0))
    assert len(q.choices) == 4
    assert len(set(q.choices)) == 4
    assert 0 <= q.answer_index < 4


# ---------------------------------------------------------------------------
# Step 2.3 — Sentence segmentation + locate-and-blank
# ---------------------------------------------------------------------------


def test_split_sentences_golden() -> None:
    result = split_sentences("猫が魚を食べた。犬が走る。")
    assert result == ["猫が魚を食べた。", "犬が走る。"]


def test_split_sentences_mixed_terminators() -> None:
    result = split_sentences("本当！嘘？終わり。")
    assert result == ["本当！", "嘘？", "終わり。"]


def test_split_sentences_newlines() -> None:
    result = split_sentences("一行目\n二行目\n")
    assert result == ["一行目\n", "二行目\n"]


def test_split_sentences_drops_blanks() -> None:
    result = split_sentences("猫。\n\n犬。")
    assert all(s.strip() for s in result)


def test_blank_target_uses_surface_of_lemma(tokenizer) -> None:
    # SudachiPy splits 食べた → 食べ (lemma 食べる) + た (auxiliary)
    blanked, removed = blank_target("猫が魚を食べた。", "食べる", tokenizer)
    assert blanked == "猫が魚を____た。"
    assert removed == "食べ"


def test_blank_target_missing_raises(tokenizer) -> None:
    with pytest.raises(ValueError):
        blank_target("猫が魚を食べた。", "飲む", tokenizer)
