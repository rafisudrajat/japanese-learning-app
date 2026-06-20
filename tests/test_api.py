import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import fsrs
from starlette.testclient import TestClient

from server.db import connect, save_card, upsert_vocab
from server.main import app, get_db

TOKEN_FIELDS = {"surface", "reading_hiragana", "lemma", "meanings", "pos", "known"}

_tmp = tempfile.mkdtemp()
_test_db_path = Path(_tmp) / "test_api.db"


def _override_db() -> sqlite3.Connection:
    return connect(_test_db_path)


app.dependency_overrides[get_db] = _override_db
client = TestClient(app)


def _reset_db() -> None:
    conn = connect(_test_db_path)
    conn.execute("DELETE FROM review_logs")
    conn.execute("DELETE FROM cards")
    conn.execute("DELETE FROM vocab")
    conn.execute("DELETE FROM texts")
    conn.commit()
    conn.close()


def test_analyze_endpoint_shape() -> None:
    resp = client.post("/analyze", json={"text": "猫を見た"})
    assert resp.status_code == 200
    data = resp.json()
    assert "tokens" in data
    assert len(data["tokens"]) > 0
    for token in data["tokens"]:
        assert set(token.keys()) == TOKEN_FIELDS
    cat = next(t for t in data["tokens"] if t["surface"] == "猫")
    assert cat["lemma"] == "猫"
    assert cat["reading_hiragana"] == "ねこ"
    assert any("cat" in m.lower() for m in cat["meanings"])
    assert cat["known"] is False


def test_analyze_endpoint_empty_text() -> None:
    resp = client.post("/analyze", json={"text": ""})
    assert resp.status_code == 200
    assert resp.json()["tokens"] == []


def test_save_word() -> None:
    _reset_db()
    resp = client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meaning": "cat", "pos": "名詞"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data

    resp2 = client.get("/vocab")
    assert any(v["lemma"] == "猫" for v in resp2.json()["vocab"])


def test_save_word_twice_is_idempotent() -> None:
    _reset_db()
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meaning": "cat", "pos": "名詞"},
    )
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meaning": "cat", "pos": "名詞"},
    )
    resp = client.get("/vocab")
    cats = [v for v in resp.json()["vocab"] if v["lemma"] == "猫"]
    assert len(cats) == 1


def test_vocab_search_filters() -> None:
    _reset_db()
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meaning": "cat", "pos": "名詞"},
    )
    client.post(
        "/vocab",
        json={"lemma": "犬", "reading": "いぬ", "meaning": "dog", "pos": "名詞"},
    )
    resp = client.get("/vocab", params={"q": "猫"})
    vocab = resp.json()["vocab"]
    assert len(vocab) == 1
    assert vocab[0]["lemma"] == "猫"


def test_vocab_search_by_reading_and_meaning() -> None:
    _reset_db()
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meaning": "cat", "pos": "名詞"},
    )
    client.post(
        "/vocab",
        json={"lemma": "犬", "reading": "いぬ", "meaning": "dog", "pos": "名詞"},
    )
    # by kana reading
    by_kana = client.get("/vocab", params={"q": "ねこ"}).json()["vocab"]
    assert [v["lemma"] for v in by_kana] == ["猫"]
    # by English meaning (case-insensitive)
    by_meaning = client.get("/vocab", params={"q": "Cat"}).json()["vocab"]
    assert [v["lemma"] for v in by_meaning] == ["猫"]
    # by kanji still works
    by_kanji = client.get("/vocab", params={"q": "犬"}).json()["vocab"]
    assert [v["lemma"] for v in by_kanji] == ["犬"]


def _create_due_card(lemma: str = "猫") -> int:
    conn = connect(_test_db_path)
    vocab_id = upsert_vocab(conn, lemma, "ねこ", "cat", "名詞", now="2025-01-01T00:00:00")
    card = fsrs.Card()
    card_db_id = save_card(conn, vocab_id, card)
    conn.close()
    return card_db_id


def test_answer_advances_and_logs() -> None:
    _reset_db()
    card_db_id = _create_due_card()

    now = datetime.now(timezone.utc).isoformat()
    queue_before = client.get("/review/queue", params={"now": now}).json()
    assert any(c["card_db_id"] == card_db_id for c in queue_before["cards"])

    resp = client.post("/review/answer", json={"card_db_id": card_db_id, "rating": 3})
    assert resp.status_code == 200

    queue_after = client.get("/review/queue", params={"now": now}).json()
    assert not any(c["card_db_id"] == card_db_id for c in queue_after["cards"])

    conn = connect(_test_db_path)
    logs = conn.execute(
        "SELECT card_id, rating FROM review_logs WHERE card_id = ?", (card_db_id,)
    ).fetchall()
    conn.close()
    assert len(logs) == 1
    assert logs[0][1] == 3


def test_queue_respects_due() -> None:
    _reset_db()
    conn = connect(_test_db_path)
    vocab_id = upsert_vocab(conn, "犬", "いぬ", "dog", "名詞", now="2025-01-01T00:00:00")
    card = fsrs.Card()
    card.__dict__["due"] = datetime(2099, 1, 1, tzinfo=timezone.utc)
    save_card(conn, vocab_id, card)
    conn.close()

    now = datetime.now(timezone.utc).isoformat()
    queue = client.get("/review/queue", params={"now": now}).json()
    assert not any(c["lemma"] == "犬" for c in queue["cards"])
