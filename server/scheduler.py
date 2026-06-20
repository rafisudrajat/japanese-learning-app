import sqlite3
from datetime import datetime
from typing import Sequence

import fsrs
from fsrs.scheduler import DEFAULT_PARAMETERS

MIN_REVIEWS_FOR_OPTIMIZATION = 100


def review(
    card: fsrs.Card,
    rating: fsrs.Rating,
    now: datetime,
    enable_fuzzing: bool = True,
    parameters: Sequence[float] | None = None,
) -> tuple[fsrs.Card, fsrs.ReviewLog]:
    kwargs: dict = {"enable_fuzzing": enable_fuzzing}
    if parameters is not None:
        kwargs["parameters"] = parameters
    scheduler = fsrs.Scheduler(**kwargs)
    return scheduler.review_card(card, rating, now)


def optimize_parameters(conn: sqlite3.Connection) -> tuple[float, ...]:
    rows = conn.execute("SELECT rating FROM review_logs").fetchall()
    if len(rows) < MIN_REVIEWS_FOR_OPTIMIZATION:
        return DEFAULT_PARAMETERS

    total = len(rows)
    good_or_easy = sum(1 for (r,) in rows if r >= 3)
    retention = good_or_easy / total

    params = list(DEFAULT_PARAMETERS)
    # Scale initial stability (indices 0-3) based on observed retention
    scale = 0.8 + 0.4 * retention
    for i in range(4):
        params[i] = DEFAULT_PARAMETERS[i] * scale
    return tuple(params)
