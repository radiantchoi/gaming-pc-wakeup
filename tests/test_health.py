from fastapi.testclient import TestClient


def test_health_returns_ok(load_main) -> None:
    client = TestClient(load_main().app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
