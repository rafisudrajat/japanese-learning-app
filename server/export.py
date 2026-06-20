import sqlite3
from pathlib import Path

import genanki

_MODEL = genanki.Model(
    1607392319,
    "Japanese Vocab",
    fields=[{"name": "Word"}, {"name": "Reading"}, {"name": "Meaning"}],
    templates=[
        {
            "name": "Card 1",
            "qfmt": "{{Word}}",
            "afmt": "{{Word}}<br>{{Reading}}<br>{{Meaning}}",
        }
    ],
)

_DECK_ID = 2059400110


def export_apkg(conn: sqlite3.Connection, path: Path) -> None:
    deck = genanki.Deck(_DECK_ID, "Japanese Vocab")
    rows = conn.execute("SELECT lemma, reading, primary_meaning FROM vocab").fetchall()
    for lemma, reading, meaning in rows:
        note = genanki.Note(
            model=_MODEL,
            fields=[lemma, reading or "", meaning or ""],
        )
        deck.add_note(note)
    pkg = genanki.Package(deck)
    pkg.write_to_file(str(path))
