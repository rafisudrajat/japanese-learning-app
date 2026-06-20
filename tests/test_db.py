import sqlite3

import pytest


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
