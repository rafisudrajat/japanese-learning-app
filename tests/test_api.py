import sqlite3
import tempfile
from pathlib import Path

from starlette.testclient import TestClient

from server.db import connect
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
    conn.execute("DELETE FROM vocab")
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
