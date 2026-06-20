from datetime import datetime

import fsrs


def review(
    card: fsrs.Card,
    rating: fsrs.Rating,
    now: datetime,
    enable_fuzzing: bool = True,
) -> tuple[fsrs.Card, fsrs.ReviewLog]:
    scheduler = fsrs.Scheduler(enable_fuzzing=enable_fuzzing)
    return scheduler.review_card(card, rating, now)
