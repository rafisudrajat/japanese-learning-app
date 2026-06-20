import sqlite3
from pathlib import Path


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
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
