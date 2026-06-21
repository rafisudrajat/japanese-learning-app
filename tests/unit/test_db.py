import sqlite3
from datetime import datetime, timezone

import fsrs
import pytest

from server.db import (
    add_vocab_meanings,
    get_setting,
    get_vocab_meanings,
    load_card,
    save_card,
    set_setting,
    update_card,
    update_vocab,
    upsert_vocab,
)
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
        upsert_vocab(db, "食べる", "たべる", "動詞", now="2025-01-01T00:00:00")
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
    upsert_vocab(db, "猫", "ねこ", "名詞", now="2025-01-01T00:00:00")
    upsert_vocab(db, "犬", "いぬ", "名詞", now="2025-01-01T00:00:00")
    count = db.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    assert count == 2


def test_card_round_trip_schedules_identically(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "名詞", now="2025-01-01T00:00:00")
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


def test_settings_table_exists(db: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "settings" in tables


def test_get_setting_returns_default_when_missing(db: sqlite3.Connection) -> None:
    assert get_setting(db, "theme") is None
    assert get_setting(db, "theme", "light") == "light"


def test_set_and_get_setting(db: sqlite3.Connection) -> None:
    set_setting(db, "theme", "dark")
    assert get_setting(db, "theme") == "dark"


def test_set_setting_overwrites(db: sqlite3.Connection) -> None:
    set_setting(db, "theme", "dark")
    set_setting(db, "theme", "light")
    assert get_setting(db, "theme") == "light"


def test_update_vocab_changes_fields(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "名詞", now="2025-01-01T00:00:00")
    add_vocab_meanings(db, vocab_id, ["cat"])
    updated = update_vocab(db, vocab_id, reading="ネコ", pos="名詞")
    assert updated is True
    row = db.execute(
        "SELECT reading, pos FROM vocab WHERE id = ?", (vocab_id,)
    ).fetchone()
    assert row == ("ネコ", "名詞")


def test_update_vocab_partial_fields(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "犬", "いぬ", "名詞", now="2025-01-01T00:00:00")
    add_vocab_meanings(db, vocab_id, ["dog"])
    update_vocab(db, vocab_id, reading="イヌ")
    row = db.execute(
        "SELECT reading FROM vocab WHERE id = ?", (vocab_id,)
    ).fetchone()
    assert row == ("イヌ",)


def test_update_vocab_missing_returns_false(db: sqlite3.Connection) -> None:
    assert update_vocab(db, 99999, reading="nope") is False


# ---------------------------------------------------------------------------
# Many-to-many: vocab <-> meanings
# ---------------------------------------------------------------------------


def test_meanings_and_junction_tables_exist(db: sqlite3.Connection) -> None:
    tables = {
        row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    assert "meanings" in tables
    assert "vocab_meanings" in tables


def test_add_and_get_vocab_meanings(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "名詞", now="2025-01-01T00:00:00")
    add_vocab_meanings(db, vocab_id, ["cat", "puss", "kitty"])
    meanings = get_vocab_meanings(db, vocab_id)
    assert set(meanings) == {"cat", "puss", "kitty"}


def test_meaning_shared_across_vocab_entries(db: sqlite3.Connection) -> None:
    id1 = upsert_vocab(db, "見る", "みる", "動詞", now="2025-01-01T00:00:00")
    id2 = upsert_vocab(db, "観る", "みる", "動詞", now="2025-01-01T00:00:00")
    add_vocab_meanings(db, id1, ["to see", "to look", "to watch"])
    add_vocab_meanings(db, id2, ["to watch", "to view"])
    meaning_ids = db.execute("SELECT id FROM meanings WHERE text = 'to watch'").fetchall()
    assert len(meaning_ids) == 1
    links = db.execute(
        "SELECT vocab_id FROM vocab_meanings WHERE meaning_id = ?", (meaning_ids[0][0],)
    ).fetchall()
    assert {r[0] for r in links} == {id1, id2}


def test_add_meanings_is_idempotent(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "名詞", now="2025-01-01T00:00:00")
    add_vocab_meanings(db, vocab_id, ["cat", "puss"])
    add_vocab_meanings(db, vocab_id, ["cat", "kitty"])
    meanings = get_vocab_meanings(db, vocab_id)
    assert set(meanings) == {"cat", "puss", "kitty"}


def test_delete_vocab_cascades_to_junction(db: sqlite3.Connection) -> None:
    from server.db import delete_vocab
    vocab_id = upsert_vocab(db, "猫", "ねこ", "名詞", now="2025-01-01T00:00:00")
    add_vocab_meanings(db, vocab_id, ["cat"])
    delete_vocab(db, vocab_id)
    links = db.execute(
        "SELECT * FROM vocab_meanings WHERE vocab_id = ?", (vocab_id,)
    ).fetchall()
    assert links == []
