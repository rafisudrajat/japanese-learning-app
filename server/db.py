import sqlite3
from pathlib import Path

import fsrs


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS texts (
            id          INTEGER PRIMARY KEY,
            title       TEXT,
            source_type TEXT,
            source_url  TEXT,
            raw_text    TEXT NOT NULL,
            analysis    TEXT,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vocab (
            id              INTEGER PRIMARY KEY,
            lemma           TEXT NOT NULL UNIQUE,
            reading         TEXT,
            primary_meaning TEXT,
            pos             TEXT,
            status          TEXT NOT NULL DEFAULT 'new',
            seen_count      INTEGER NOT NULL DEFAULT 0,
            text_count      INTEGER NOT NULL DEFAULT 0,
            first_seen_text_id INTEGER REFERENCES texts(id),
            created_at      TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cards (
            id          INTEGER PRIMARY KEY,
            vocab_id    INTEGER NOT NULL REFERENCES vocab(id),
            card_id     INTEGER NOT NULL,
            state       INTEGER NOT NULL DEFAULT 1,
            step        INTEGER NOT NULL DEFAULT 0,
            stability   REAL,
            difficulty  REAL,
            due         TEXT NOT NULL,
            last_review TEXT
        );

        CREATE TABLE IF NOT EXISTS review_logs (
            id          INTEGER PRIMARY KEY,
            card_id     INTEGER NOT NULL REFERENCES cards(id),
            rating      INTEGER NOT NULL,
            reviewed_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


def upsert_vocab(
    conn: sqlite3.Connection,
    lemma: str,
    reading: str,
    meaning: str,
    pos: str,
    text_id: int | None = None,
    now: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO vocab (lemma, reading, primary_meaning, pos, seen_count, text_count,
                           first_seen_text_id, created_at)
        VALUES (?, ?, ?, ?, 1, 1, ?, ?)
        ON CONFLICT (lemma) DO UPDATE SET
            seen_count = seen_count + 1
        RETURNING id
        """,
        (lemma, reading, meaning, pos, text_id, now),
    )
    row = cur.fetchone()
    conn.commit()
    return row[0]


def delete_vocab(conn: sqlite3.Connection, vocab_id: int) -> bool:
    conn.execute(
        "DELETE FROM review_logs WHERE card_id IN "
        "(SELECT id FROM cards WHERE vocab_id = ?)",
        (vocab_id,),
    )
    conn.execute("DELETE FROM cards WHERE vocab_id = ?", (vocab_id,))
    cur = conn.execute("DELETE FROM vocab WHERE id = ?", (vocab_id,))
    conn.commit()
    return cur.rowcount > 0


def save_card(conn: sqlite3.Connection, vocab_id: int, card: fsrs.Card) -> int:
    d = card.to_dict()
    cur = conn.execute(
        """
        INSERT INTO cards (vocab_id, card_id, state, step, stability, difficulty, due, last_review)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (
            vocab_id,
            d["card_id"],
            d["state"],
            d.get("step", 0) or 0,
            d["stability"],
            d["difficulty"],
            d["due"],
            d["last_review"],
        ),
    )
    row = cur.fetchone()
    if row is None:
        cur = conn.execute("SELECT id FROM cards WHERE vocab_id = ?", (vocab_id,))
        row = cur.fetchone()
    conn.commit()
    return row[0]


def update_card(conn: sqlite3.Connection, card_db_id: int, card: fsrs.Card) -> None:
    d = card.to_dict()
    conn.execute(
        """
        UPDATE cards SET state=?, step=?, stability=?, difficulty=?, due=?, last_review=?
        WHERE id=?
        """,
        (
            d["state"],
            d.get("step", 0) or 0,
            d["stability"],
            d["difficulty"],
            d["due"],
            d["last_review"],
            card_db_id,
        ),
    )
    conn.commit()


def load_card(conn: sqlite3.Connection, card_db_id: int) -> fsrs.Card:
    row = conn.execute(
        "SELECT card_id, state, step, stability, difficulty, due, last_review FROM cards WHERE id=?",
        (card_db_id,),
    ).fetchone()
    return fsrs.Card.from_dict(
        {
            "card_id": row[0],
            "state": row[1],
            "step": row[2],
            "stability": row[3],
            "difficulty": row[4],
            "due": row[5],
            "last_review": row[6],
        }
    )
