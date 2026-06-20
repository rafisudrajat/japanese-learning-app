import sqlite3

from server.db import save_card, upsert_vocab
from server.stats import compute_stats

import fsrs


def test_accuracy_from_logs(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "cat", "名詞", now="2025-01-01")
    card_db_id = save_card(db, vocab_id, fsrs.Card())
    for rating in [3, 3, 3, 1]:
        db.execute(
            "INSERT INTO review_logs (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
            (card_db_id, rating, "2025-06-01T00:00:00"),
        )
    db.commit()

    stats = compute_stats(db)
    assert stats.accuracy == 0.75


def test_reviews_per_day_buckets(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "cat", "名詞", now="2025-01-01")
    card_db_id = save_card(db, vocab_id, fsrs.Card())
    db.execute(
        "INSERT INTO review_logs (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
        (card_db_id, 3, "2025-06-01T10:00:00"),
    )
    db.execute(
        "INSERT INTO review_logs (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
        (card_db_id, 3, "2025-06-01T11:00:00"),
    )
    db.execute(
        "INSERT INTO review_logs (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
        (card_db_id, 4, "2025-06-02T10:00:00"),
    )
    db.commit()

    stats = compute_stats(db)
    assert stats.reviews_per_day["2025-06-01"] == 2
    assert stats.reviews_per_day["2025-06-02"] == 1
