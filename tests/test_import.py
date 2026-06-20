from tests.test_api import _reset_db, _test_db_path, client

from server.db import connect


def test_keep_creates_one_card() -> None:
    _reset_db()
    client.post(
        "/triage",
        json={
            "lemma": "猫",
            "reading": "ねこ",
            "meaning": "cat",
            "pos": "名詞",
            "decision": "keep",
        },
    )
    conn = connect(_test_db_path)
    cards = conn.execute("SELECT id FROM cards").fetchall()
    assert len(cards) == 1

    client.post(
        "/triage",
        json={
            "lemma": "猫",
            "reading": "ねこ",
            "meaning": "cat",
            "pos": "名詞",
            "decision": "keep",
        },
    )
    cards = conn.execute("SELECT id FROM cards").fetchall()
    conn.close()
    assert len(cards) == 1


def test_known_creates_no_card() -> None:
    _reset_db()
    client.post(
        "/triage",
        json={
            "lemma": "犬",
            "reading": "いぬ",
            "meaning": "dog",
            "pos": "名詞",
            "decision": "known",
        },
    )
    conn = connect(_test_db_path)
    cards = conn.execute("SELECT id FROM cards").fetchall()
    vocab = conn.execute("SELECT status FROM vocab WHERE lemma = '犬'").fetchone()
    conn.close()
    assert len(cards) == 0
    assert vocab[0] == "known"
