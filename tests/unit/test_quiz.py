import random

from server.quiz import VocabEntry, sample_one


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
