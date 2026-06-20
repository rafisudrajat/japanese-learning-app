from starlette.testclient import TestClient

from server.main import app

client = TestClient(app)

TOKEN_FIELDS = {"surface", "reading_hiragana", "lemma", "meanings", "pos", "known"}


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
