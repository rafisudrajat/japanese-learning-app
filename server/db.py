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

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meanings (
            id   INTEGER PRIMARY KEY,
            text TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS vocab_meanings (
            vocab_id   INTEGER NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
            meaning_id INTEGER NOT NULL REFERENCES meanings(id) ON DELETE CASCADE,
            PRIMARY KEY (vocab_id, meaning_id)
        );
    """)
    conn.commit()
    _migrate_primary_meanings(conn)
    return conn


def _migrate_primary_meanings(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, primary_meaning FROM vocab "
        "WHERE primary_meaning IS NOT NULL AND primary_meaning != '' "
        "AND id NOT IN (SELECT DISTINCT vocab_id FROM vocab_meanings)"
    ).fetchall()
    if not rows:
        return
    for vocab_id, meaning_text in rows:
        for m in meaning_text.split("; "):
            m = m.strip()
            if not m:
                continue
            conn.execute(
                "INSERT INTO meanings (text) VALUES (?) ON CONFLICT (text) DO NOTHING",
                (m,),
            )
            meaning_id = conn.execute(
                "SELECT id FROM meanings WHERE text = ?", (m,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO vocab_meanings (vocab_id, meaning_id) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING",
                (vocab_id, meaning_id),
            )
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def upsert_vocab(
    conn: sqlite3.Connection,
    lemma: str,
    reading: str,
    pos: str,
    text_id: int | None = None,
    now: str = "",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO vocab (lemma, reading, pos, seen_count, text_count,
                           first_seen_text_id, created_at)
        VALUES (?, ?, ?, 1, 1, ?, ?)
        ON CONFLICT (lemma) DO UPDATE SET
            seen_count = seen_count + 1
        RETURNING id
        """,
        (lemma, reading, pos, text_id, now),
    )
    row = cur.fetchone()
    conn.commit()
    return row[0]


def update_vocab(
    conn: sqlite3.Connection,
    vocab_id: int,
    reading: str | None = None,
    pos: str | None = None,
) -> bool:
    updates: list[str] = []
    params: list[str] = []
    if reading is not None:
        updates.append("reading = ?")
        params.append(reading)
    if pos is not None:
        updates.append("pos = ?")
        params.append(pos)
    if not updates:
        return False
    params.append(str(vocab_id))
    cur = conn.execute(
        f"UPDATE vocab SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    conn.commit()
    return cur.rowcount > 0


def add_vocab_meanings(
    conn: sqlite3.Connection, vocab_id: int, meanings: list[str]
) -> None:
    for text in meanings:
        conn.execute(
            "INSERT INTO meanings (text) VALUES (?) ON CONFLICT (text) DO NOTHING",
            (text,),
        )
        meaning_id = conn.execute(
            "SELECT id FROM meanings WHERE text = ?", (text,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO vocab_meanings (vocab_id, meaning_id) VALUES (?, ?) "
            "ON CONFLICT DO NOTHING",
            (vocab_id, meaning_id),
        )
    conn.commit()


def set_vocab_meanings(
    conn: sqlite3.Connection, vocab_id: int, meanings: list[str]
) -> None:
    conn.execute("DELETE FROM vocab_meanings WHERE vocab_id = ?", (vocab_id,))
    add_vocab_meanings(conn, vocab_id, meanings)


def get_vocab_meanings(conn: sqlite3.Connection, vocab_id: int) -> list[str]:
    rows = conn.execute(
        "SELECT m.text FROM meanings m "
        "JOIN vocab_meanings vm ON m.id = vm.meaning_id "
        "WHERE vm.vocab_id = ?",
        (vocab_id,),
    ).fetchall()
    return [r[0] for r in rows]


def delete_vocab(conn: sqlite3.Connection, vocab_id: int) -> bool:
    conn.execute(
        "DELETE FROM review_logs WHERE card_id IN "
        "(SELECT id FROM cards WHERE vocab_id = ?)",
        (vocab_id,),
    )
    conn.execute("DELETE FROM cards WHERE vocab_id = ?", (vocab_id,))
    conn.execute("DELETE FROM vocab_meanings WHERE vocab_id = ?", (vocab_id,))
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
