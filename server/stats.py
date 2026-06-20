import sqlite3
from collections import Counter
from dataclasses import dataclass


@dataclass
class Stats:
    accuracy: float
    total_reviews: int
    reviews_per_day: dict[str, int]


def compute_stats(conn: sqlite3.Connection) -> Stats:
    rows = conn.execute("SELECT rating, reviewed_at FROM review_logs").fetchall()
    total = len(rows)
    if total == 0:
        return Stats(accuracy=0.0, total_reviews=0, reviews_per_day={})

    correct = sum(1 for rating, _ in rows if rating >= 3)
    accuracy = correct / total

    day_counts: Counter[str] = Counter()
    for _, reviewed_at in rows:
        day = reviewed_at[:10]
        day_counts[day] += 1

    return Stats(
        accuracy=accuracy,
        total_reviews=total,
        reviews_per_day=dict(sorted(day_counts.items())),
    )
