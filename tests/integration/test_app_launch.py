from starlette.testclient import TestClient


def test_server_serves_reader(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text-input" in resp.text
