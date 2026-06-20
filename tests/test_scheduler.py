from datetime import datetime, timezone

import fsrs

from server.scheduler import review


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
