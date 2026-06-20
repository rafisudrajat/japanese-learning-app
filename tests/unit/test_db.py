import sqlite3
from datetime import datetime, timezone

import fsrs
import pytest

from server.db import load_card, save_card, update_card, upsert_vocab
from server.scheduler import review


def test_schema_creates_tables(db: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
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


def test_cards_and_logs_schema(db: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "cards" in tables
    assert "review_logs" in tables

    card_cols = {row[1] for row in db.execute("PRAGMA table_info(cards)").fetchall()}
    assert "vocab_id" in card_cols
    assert "state" in card_cols
    assert "stability" in card_cols
    assert "difficulty" in card_cols
    assert "due" in card_cols
    assert "last_review" in card_cols

    log_cols = {row[1] for row in db.execute("PRAGMA table_info(review_logs)").fetchall()}
    assert "card_id" in log_cols
    assert "rating" in log_cols
    assert "reviewed_at" in log_cols


def test_distinct_lemmas_create_distinct_rows(db: sqlite3.Connection) -> None:
    upsert_vocab(db, "猫", "ねこ", "cat", "名詞", now="2025-01-01T00:00:00")
    upsert_vocab(db, "犬", "いぬ", "dog", "名詞", now="2025-01-01T00:00:00")
    count = db.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    assert count == 2


def test_card_round_trip_schedules_identically(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "cat", "名詞", now="2025-01-01T00:00:00")
    now1 = datetime(2025, 6, 1, tzinfo=timezone.utc)
    card = fsrs.Card()
    reviewed, _log = review(card, fsrs.Rating.Good, now1, enable_fuzzing=False)

    card_db_id = save_card(db, vocab_id, reviewed)
    update_card(db, card_db_id, reviewed)
    loaded = load_card(db, card_db_id)

    now2 = datetime(2025, 6, 2, tzinfo=timezone.utc)
    card_a, _ = review(reviewed, fsrs.Rating.Good, now2, enable_fuzzing=False)
    card_b, _ = review(loaded, fsrs.Rating.Good, now2, enable_fuzzing=False)

    assert card_a.due == card_b.due
    assert card_a.stability == card_b.stability
    assert card_a.difficulty == card_b.difficulty
