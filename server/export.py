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
    rows = conn.execute("SELECT id, lemma, reading FROM vocab").fetchall()
    for vocab_id, lemma, reading in rows:
        meanings_rows = conn.execute(
            "SELECT m.text FROM meanings m "
            "JOIN vocab_meanings vm ON m.id = vm.meaning_id "
            "WHERE vm.vocab_id = ?",
            (vocab_id,),
        ).fetchall()
        meaning_str = "; ".join(r[0] for r in meanings_rows)
        note = genanki.Note(
            model=_MODEL,
            fields=[lemma, reading or "", meaning_str],
        )
        deck.add_note(note)
    pkg = genanki.Package(deck)
    pkg.write_to_file(str(path))
