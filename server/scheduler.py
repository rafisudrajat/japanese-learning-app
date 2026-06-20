from datetime import datetime

import fsrs


def review(card: fsrs.Card, rating: fsrs.Rating, now: datetime) -> tuple[fsrs.Card, fsrs.ReviewLog]:
    scheduler = fsrs.Scheduler()
    return scheduler.review_card(card, rating, now)
