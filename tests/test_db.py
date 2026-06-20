import sqlite3

import pytest

from server.db import upsert_vocab


def test_schema_creates_tables(db: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "texts" in tables
    assert "vocab" in tables

    vocab_cols = {row[1] for row in db.execute("PRAGMA table_info(vocab)").fetchall()}
    assert "lemma" in vocab_cols
    assert "status" in vocab_cols
    assert "seen_count" in vocab_cols


def test_lemma_unique_constraint(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO vocab (lemma, created_at) VALUES (?, ?)",
        ("猫", "2025-01-01T00:00:00"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO vocab (lemma, created_at) VALUES (?, ?)",
            ("猫", "2025-01-01T00:00:00"),
        )


def test_inflections_dedupe_to_one_row(db: sqlite3.Connection) -> None:
    for _ in range(3):
        upsert_vocab(db, "食べる", "たべる", "eat", "動詞", now="2025-01-01T00:00:00")
    rows = db.execute("SELECT seen_count FROM vocab WHERE lemma = '食べる'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 3


def test_distinct_lemmas_create_distinct_rows(db: sqlite3.Connection) -> None:
    upsert_vocab(db, "猫", "ねこ", "cat", "名詞", now="2025-01-01T00:00:00")
    upsert_vocab(db, "犬", "いぬ", "dog", "名詞", now="2025-01-01T00:00:00")
    count = db.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    assert count == 2
