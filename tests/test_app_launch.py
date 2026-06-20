from starlette.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_server_serves_reader() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text-input" in resp.text
