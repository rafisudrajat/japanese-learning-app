from pathlib import Path

from starlette.testclient import TestClient

from server.db import connect

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_keep_creates_one_card(client: TestClient, api_db: Path) -> None:
    client.post(
        "/triage",
        json={
            "lemma": "猫",
            "reading": "ねこ",
            "meanings": ["cat"],
            "pos": "名詞",
            "decision": "keep",
        },
    )
    conn = connect(api_db)
    cards = conn.execute("SELECT id FROM cards").fetchall()
    assert len(cards) == 1

    client.post(
        "/triage",
        json={
            "lemma": "猫",
            "reading": "ねこ",
            "meanings": ["cat"],
            "pos": "名詞",
            "decision": "keep",
        },
    )
    cards = conn.execute("SELECT id FROM cards").fetchall()
    conn.close()
    assert len(cards) == 1


def test_known_creates_no_card(client: TestClient, api_db: Path) -> None:
    client.post(
        "/triage",
        json={
            "lemma": "犬",
            "reading": "いぬ",
            "meanings": ["dog"],
            "pos": "名詞",
            "decision": "known",
        },
    )
    conn = connect(api_db)
    cards = conn.execute("SELECT id FROM cards").fetchall()
    vocab = conn.execute("SELECT status FROM vocab WHERE lemma = '犬'").fetchone()
    conn.close()
    assert len(cards) == 0
    assert vocab[0] == "known"


def test_paste_persists_text(client: TestClient, api_db: Path) -> None:
    resp = client.post(
        "/import/paste",
        json={"title": "Test Article", "text": "猫が魚を食べた"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "text_id" in data
    assert data["text_id"] > 0

    conn = connect(api_db)
    row = conn.execute(
        "SELECT source_type, raw_text FROM texts WHERE id = ?", (data["text_id"],)
    ).fetchone()
    conn.close()
    assert row[0] == "paste"
    assert row[1] == "猫が魚を食べた"


def test_paste_returns_candidates(client: TestClient, api_db: Path) -> None:
    resp = client.post(
        "/import/paste",
        json={"title": "Test", "text": "猫が魚を食べた"},
    )
    data = resp.json()
    assert len(data["tokens"]) > 0
    assert len(data["candidates"]) > 0
    candidate_lemmas = {c["lemma"] for c in data["candidates"]}
    assert "猫" in candidate_lemmas or "魚" in candidate_lemmas or "食べる" in candidate_lemmas


def test_already_know_suppresses_future(client: TestClient, api_db: Path) -> None:
    client.post(
        "/triage",
        json={"lemma": "猫", "reading": "ねこ", "meanings": ["cat"], "pos": "名詞", "decision": "known"},
    )
    resp = client.post(
        "/import/paste",
        json={"title": "Test", "text": "猫が魚を食べた"},
    )
    candidate_lemmas = {c["lemma"] for c in resp.json()["candidates"]}
    assert "猫" not in candidate_lemmas


def test_dom_import_runs_pipeline(client: TestClient, api_db: Path) -> None:
    html = (FIXTURES / "article_with_nav.html").read_text()
    resp = client.post("/import/dom", json={"html": html})
    assert resp.status_code == 200
    data = resp.json()
    assert data["text_id"] > 0
    assert len(data["tokens"]) > 0
