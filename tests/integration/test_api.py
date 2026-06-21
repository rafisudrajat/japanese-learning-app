from datetime import datetime, timezone
from pathlib import Path

import fsrs
from starlette.testclient import TestClient

from server.db import add_vocab_meanings, connect, save_card, upsert_vocab

TOKEN_FIELDS = {"surface", "reading_hiragana", "lemma", "meanings", "pos", "known"}


def test_analyze_endpoint_shape(client: TestClient, api_db: Path) -> None:
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


def test_analyze_endpoint_empty_text(client: TestClient, api_db: Path) -> None:
    resp = client.post("/analyze", json={"text": ""})
    assert resp.status_code == 200
    assert resp.json()["tokens"] == []


def test_save_word(client: TestClient, api_db: Path) -> None:
    resp = client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meanings": ["cat"], "pos": "名詞"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data

    resp2 = client.get("/vocab")
    vocab = resp2.json()["vocab"]
    assert any(v["lemma"] == "猫" for v in vocab)
    cat = next(v for v in vocab if v["lemma"] == "猫")
    assert cat["meanings"] == ["cat"]


def test_save_word_twice_is_idempotent(client: TestClient, api_db: Path) -> None:
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meanings": ["cat"], "pos": "名詞"},
    )
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meanings": ["cat"], "pos": "名詞"},
    )
    resp = client.get("/vocab")
    cats = [v for v in resp.json()["vocab"] if v["lemma"] == "猫"]
    assert len(cats) == 1


def test_vocab_search_filters(client: TestClient, api_db: Path) -> None:
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meanings": ["cat"], "pos": "名詞"},
    )
    client.post(
        "/vocab",
        json={"lemma": "犬", "reading": "いぬ", "meanings": ["dog"], "pos": "名詞"},
    )
    resp = client.get("/vocab", params={"q": "猫"})
    vocab = resp.json()["vocab"]
    assert len(vocab) == 1
    assert vocab[0]["lemma"] == "猫"


def test_vocab_search_by_reading_and_meaning(client: TestClient, api_db: Path) -> None:
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meanings": ["cat"], "pos": "名詞"},
    )
    client.post(
        "/vocab",
        json={"lemma": "犬", "reading": "いぬ", "meanings": ["dog"], "pos": "名詞"},
    )
    by_kana = client.get("/vocab", params={"q": "ねこ"}).json()["vocab"]
    assert [v["lemma"] for v in by_kana] == ["猫"]
    by_meaning = client.get("/vocab", params={"q": "Cat"}).json()["vocab"]
    assert [v["lemma"] for v in by_meaning] == ["猫"]
    by_kanji = client.get("/vocab", params={"q": "犬"}).json()["vocab"]
    assert [v["lemma"] for v in by_kanji] == ["犬"]


def test_answer_advances_and_logs(client: TestClient, api_db: Path, make_due_card) -> None:
    card_db_id = make_due_card()

    now = datetime.now(timezone.utc).isoformat()
    queue_before = client.get("/review/queue", params={"now": now}).json()
    assert any(c["card_db_id"] == card_db_id for c in queue_before["cards"])

    resp = client.post("/review/answer", json={"card_db_id": card_db_id, "rating": 3})
    assert resp.status_code == 200

    queue_after = client.get("/review/queue", params={"now": now}).json()
    assert not any(c["card_db_id"] == card_db_id for c in queue_after["cards"])

    conn = connect(api_db)
    logs = conn.execute(
        "SELECT card_id, rating FROM review_logs WHERE card_id = ?", (card_db_id,)
    ).fetchall()
    conn.close()
    assert len(logs) == 1
    assert logs[0][1] == 3


def test_delete_vocab_removes_word_and_cascades(
    client: TestClient, api_db: Path, make_due_card
) -> None:
    card_db_id = make_due_card("猫")
    client.post("/review/answer", json={"card_db_id": card_db_id, "rating": 3})

    vocab = client.get("/vocab").json()["vocab"]
    assert len(vocab) == 1
    vocab_id = vocab[0]["id"]

    resp = client.delete(f"/vocab/{vocab_id}")
    assert resp.status_code == 200

    assert client.get("/vocab").json()["vocab"] == []

    conn = connect(api_db)
    cards = conn.execute("SELECT id FROM cards WHERE vocab_id = ?", (vocab_id,)).fetchall()
    logs = conn.execute("SELECT id FROM review_logs WHERE card_id = ?", (card_db_id,)).fetchall()
    conn.close()
    assert cards == []
    assert logs == []


def test_delete_missing_vocab_returns_404(client: TestClient, api_db: Path) -> None:
    resp = client.delete("/vocab/99999")
    assert resp.status_code == 404


def test_queue_respects_due(client: TestClient, api_db: Path) -> None:
    conn = connect(api_db)
    vocab_id = upsert_vocab(conn, "犬", "いぬ", "名詞", now="2025-01-01T00:00:00")
    card = fsrs.Card()
    card.__dict__["due"] = datetime(2099, 1, 1, tzinfo=timezone.utc)
    save_card(conn, vocab_id, card)
    conn.close()

    now = datetime.now(timezone.utc).isoformat()
    queue = client.get("/review/queue", params={"now": now}).json()
    assert not any(c["lemma"] == "犬" for c in queue["cards"])


# ---------------------------------------------------------------------------
# Step 4.1 — GET /quiz/next
# ---------------------------------------------------------------------------

_QUIZ_VOCAB = [
    ("猫", "ねこ", "cat", "名詞"),
    ("犬", "いぬ", "dog", "名詞"),
    ("鳥", "とり", "bird", "名詞"),
    ("魚", "さかな", "fish", "名詞"),
    ("本", "ほん", "book", "名詞"),
    ("花", "はな", "flower", "名詞"),
]

QUIZ_QUESTION_FIELDS = {"question_id", "kind", "prompt", "choices", "context_html"}


def _seed_quiz_vocab(db_path: Path) -> None:
    conn = connect(db_path)
    for lemma, reading, meaning, pos in _QUIZ_VOCAB:
        vocab_id = upsert_vocab(conn, lemma, reading, pos, now="2025-01-01T00:00:00")
        add_vocab_meanings(conn, vocab_id, [meaning])
        conn.execute("UPDATE vocab SET status = 'learning' WHERE id = ?", (vocab_id,))
    conn.commit()
    conn.close()


def test_quiz_next_shape(client: TestClient, api_db: Path) -> None:
    _seed_quiz_vocab(api_db)
    resp = client.get("/quiz/next", params={"type": "meaning"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == QUIZ_QUESTION_FIELDS
    assert len(data["choices"]) == 4
    assert "answer_index" not in data


def test_quiz_next_reading_prompt_has_kanji(client: TestClient, api_db: Path) -> None:
    _seed_quiz_vocab(api_db)
    resp = client.get("/quiz/next", params={"type": "reading"})
    assert resp.status_code == 200
    prompt = resp.json()["prompt"]
    assert any("一" <= c <= "鿿" for c in prompt)


def test_quiz_next_too_few_vocab_400(client: TestClient, api_db: Path) -> None:
    conn = connect(api_db)
    upsert_vocab(conn, "猫", "ねこ", "名詞", now="2025-01-01T00:00:00")
    conn.execute("UPDATE vocab SET status = 'learning' WHERE lemma = '猫'")
    conn.commit()
    conn.close()
    resp = client.get("/quiz/next", params={"type": "meaning"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Step 4.2 — POST /quiz/answer
# ---------------------------------------------------------------------------


def test_quiz_answer_correct_flow(client: TestClient, api_db: Path) -> None:
    _seed_quiz_vocab(api_db)
    q = client.get("/quiz/next", params={"type": "meaning"}).json()
    qid = q["question_id"]
    choices = q["choices"]

    resp = client.post("/quiz/answer", json={"question_id": qid, "choice_index": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert "correct" in data
    assert "correct_index" in data
    assert "correct_answer" in data
    assert data["correct_answer"] == choices[data["correct_index"]]
    if data["correct_index"] == 0:
        assert data["correct"] is True
    else:
        assert data["correct"] is False


def test_quiz_answer_unknown_id_404(client: TestClient, api_db: Path) -> None:
    resp = client.post(
        "/quiz/answer",
        json={"question_id": "00000000-0000-0000-0000-000000000000", "choice_index": 0},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Step 4.3 — (Optional) feed results into FSRS
# ---------------------------------------------------------------------------


def _seed_quiz_vocab_with_cards(db_path: Path) -> None:
    conn = connect(db_path)
    for lemma, reading, meaning, pos in _QUIZ_VOCAB:
        vocab_id = upsert_vocab(conn, lemma, reading, pos, now="2025-01-01T00:00:00")
        add_vocab_meanings(conn, vocab_id, [meaning])
        conn.execute("UPDATE vocab SET status = 'learning' WHERE id = ?", (vocab_id,))
        save_card(conn, vocab_id, fsrs.Card())
    conn.commit()
    conn.close()


def test_quiz_answer_updates_review_log(client: TestClient, api_db: Path) -> None:
    _seed_quiz_vocab_with_cards(api_db)

    q = client.get("/quiz/next", params={"type": "meaning"}).json()

    resp = client.post(
        "/quiz/answer",
        json={
            "question_id": q["question_id"],
            "choice_index": 0,
            "count_as_review": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    expected_rating = 3 if data["correct"] else 1

    conn = connect(api_db)
    logs = conn.execute("SELECT rating FROM review_logs").fetchall()
    conn.close()
    assert len(logs) == 1
    assert logs[0][0] == expected_rating


# ---------------------------------------------------------------------------
# Step 5.1 — GET /quiz-page
# ---------------------------------------------------------------------------


def test_quiz_page_served(client: TestClient) -> None:
    resp = client.get("/quiz-page")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "quiz.js" in resp.text


# ---------------------------------------------------------------------------
# Dark mode — theme settings API
# ---------------------------------------------------------------------------


def test_get_theme_returns_light_by_default(client: TestClient, api_db: Path) -> None:
    resp = client.get("/api/settings/theme")
    assert resp.status_code == 200
    assert resp.json()["theme"] == "light"


def test_put_theme_persists(client: TestClient, api_db: Path) -> None:
    resp = client.put("/api/settings/theme", json={"theme": "dark"})
    assert resp.status_code == 200
    assert resp.json()["theme"] == "dark"

    resp2 = client.get("/api/settings/theme")
    assert resp2.json()["theme"] == "dark"


def test_put_theme_rejects_invalid_value(client: TestClient, api_db: Path) -> None:
    resp = client.put("/api/settings/theme", json={"theme": "neon"})
    assert resp.status_code == 422


def test_all_pages_include_theme_toggle(client: TestClient) -> None:
    pages = ["/", "/vocab-page", "/review-page", "/quiz-page", "/stats-page", "/import-page"]
    for page in pages:
        resp = client.get(page)
        assert resp.status_code == 200
        assert "theme-toggle" in resp.text, f"{page} missing theme toggle button"
        assert "theme.js" in resp.text, f"{page} missing theme.js script"


# ---------------------------------------------------------------------------
# Edit vocabulary
# ---------------------------------------------------------------------------


def test_edit_vocab_updates_fields(client: TestClient, api_db: Path) -> None:
    client.post(
        "/vocab",
        json={"lemma": "猫", "reading": "ねこ", "meanings": ["cat"], "pos": "名詞"},
    )
    vocab_id = client.get("/vocab").json()["vocab"][0]["id"]

    resp = client.put(
        f"/vocab/{vocab_id}",
        json={"reading": "ネコ", "meanings": ["cat", "kitty"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["reading"] == "ネコ"
    assert set(data["meanings"]) == {"cat", "kitty"}

    updated = client.get("/vocab").json()["vocab"][0]
    assert updated["reading"] == "ネコ"
    assert set(updated["meanings"]) == {"cat", "kitty"}


def test_edit_vocab_partial_update(client: TestClient, api_db: Path) -> None:
    client.post(
        "/vocab",
        json={"lemma": "犬", "reading": "いぬ", "meanings": ["dog"], "pos": "名詞"},
    )
    vocab_id = client.get("/vocab").json()["vocab"][0]["id"]

    resp = client.put(f"/vocab/{vocab_id}", json={"meanings": ["dog", "puppy"]})
    assert resp.status_code == 200
    updated = client.get("/vocab").json()["vocab"][0]
    assert updated["reading"] == "いぬ"
    assert set(updated["meanings"]) == {"dog", "puppy"}


def test_edit_missing_vocab_returns_404(client: TestClient, api_db: Path) -> None:
    resp = client.put("/vocab/99999", json={"reading": "nope"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Manual add vocabulary
# ---------------------------------------------------------------------------


def test_manual_add_vocab(client: TestClient, api_db: Path) -> None:
    resp = client.post(
        "/vocab",
        json={"lemma": "空", "reading": "そら", "meanings": ["sky"], "pos": "名詞"},
    )
    assert resp.status_code == 200
    assert resp.json()["created"] is True

    vocab = client.get("/vocab").json()["vocab"]
    sky = next(v for v in vocab if v["lemma"] == "空")
    assert sky["meanings"] == ["sky"]


def test_triage_saves_all_meanings(client: TestClient, api_db: Path) -> None:
    client.post("/analyze", json={"text": "猫を見た"})
    resp = client.post(
        "/triage",
        json={
            "lemma": "猫",
            "reading": "ねこ",
            "meanings": ["cat", "puss", "kitty"],
            "pos": "名詞",
            "decision": "keep",
        },
    )
    assert resp.status_code == 200

    vocab = client.get("/vocab").json()["vocab"]
    cat = next(v for v in vocab if v["lemma"] == "猫")
    assert set(cat["meanings"]) == {"cat", "puss", "kitty"}


def test_manual_add_duplicate_is_idempotent(client: TestClient, api_db: Path) -> None:
    client.post(
        "/vocab",
        json={"lemma": "山", "reading": "やま", "meanings": ["mountain"], "pos": "名詞"},
    )
    resp2 = client.post(
        "/vocab",
        json={"lemma": "山", "reading": "やま", "meanings": ["mountain"], "pos": "名詞"},
    )
    assert resp2.json()["created"] is False
    vocab = client.get("/vocab").json()["vocab"]
    mountains = [v for v in vocab if v["lemma"] == "山"]
    assert len(mountains) == 1


def test_vocab_many_to_many_reverse_lookup(client: TestClient, api_db: Path) -> None:
    """One English meaning shared by multiple Japanese words is searchable."""
    client.post(
        "/vocab",
        json={"lemma": "見る", "reading": "みる", "meanings": ["to see", "to watch"], "pos": "動詞"},
    )
    client.post(
        "/vocab",
        json={"lemma": "観る", "reading": "みる", "meanings": ["to watch", "to view"], "pos": "動詞"},
    )
    results = client.get("/vocab", params={"q": "to watch"}).json()["vocab"]
    lemmas = {v["lemma"] for v in results}
    assert lemmas == {"見る", "観る"}
