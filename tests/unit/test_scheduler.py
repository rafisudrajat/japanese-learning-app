import sqlite3
from datetime import datetime, timezone

import fsrs
from fsrs.scheduler import DEFAULT_PARAMETERS

from server.db import save_card, upsert_vocab
from server.scheduler import optimize_parameters, review


def test_due_in_future_and_reps_increment() -> None:
    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    card = fsrs.Card()
    new_card, _log = review(card, fsrs.Rating.Good, now)
    assert new_card.due > now
    assert new_card.step == 1


def test_again_schedules_sooner_than_easy() -> None:
    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    card_again, _ = review(fsrs.Card(), fsrs.Rating.Again, now)
    card_easy, _ = review(fsrs.Card(), fsrs.Rating.Easy, now)
    assert card_again.due < card_easy.due


def test_optimized_scheduler_keeps_invariants(db: sqlite3.Connection) -> None:
    vocab_id = upsert_vocab(db, "猫", "ねこ", "cat", "名詞", now="2025-01-01")
    card_db_id = save_card(db, vocab_id, fsrs.Card())
    for i in range(120):
        rating = 3 if i % 4 != 0 else 1
        db.execute(
            "INSERT INTO review_logs (card_id, rating, reviewed_at) VALUES (?, ?, ?)",
            (card_db_id, rating, f"2025-01-{(i % 28) + 1:02d}T00:00:00"),
        )
    db.commit()

    params = optimize_parameters(db)
    assert params != DEFAULT_PARAMETERS

    now = datetime(2025, 6, 1, tzinfo=timezone.utc)
    card = fsrs.Card()
    new_card, _ = review(card, fsrs.Rating.Good, now, parameters=params)
    assert new_card.due > now

    card_again, _ = review(fsrs.Card(), fsrs.Rating.Again, now, parameters=params)
    card_easy, _ = review(fsrs.Card(), fsrs.Rating.Easy, now, parameters=params)
    assert card_again.due < card_easy.due


def test_insufficient_history_uses_defaults(db: sqlite3.Connection) -> None:
    params = optimize_parameters(db)
    assert params == DEFAULT_PARAMETERS
