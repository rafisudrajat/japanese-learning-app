import sqlite3
import zipfile
from pathlib import Path

from server.db import upsert_vocab
from server.export import export_apkg


def test_apkg_written_with_notes(db: sqlite3.Connection, tmp_path: Path) -> None:
    for lemma, reading, meaning in [
        ("猫", "ねこ", "cat"),
        ("犬", "いぬ", "dog"),
        ("魚", "さかな", "fish"),
    ]:
        upsert_vocab(db, lemma, reading, meaning, "名詞", now="2025-01-01")

    apkg_path = tmp_path / "export.apkg"
    export_apkg(db, apkg_path)

    assert apkg_path.exists()
    assert apkg_path.stat().st_size > 0

    with zipfile.ZipFile(str(apkg_path)) as z:
        z.extract("collection.anki2", path=str(tmp_path))
    anki_db = sqlite3.connect(str(tmp_path / "collection.anki2"))
    note_count = anki_db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    anki_db.close()
    assert note_count == 3
