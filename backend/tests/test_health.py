import pytest
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_live(client):
    r = client.get("/health/live")
    assert r.status_code == 200 and r.json()["status"] == "alive"
    assert r.headers["x-request-id"]


def test_ready_is_not_ready_without_worker(client):
    r = client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "NOT_READY"
    assert body["components"]["worker"] == "UNKNOWN"


def test_error_envelope_404_and_request_id(client):
    r = client.get("/nope", headers={"X-Request-ID": "abcdef123456"})
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "NOT_FOUND" and err["request_id"] == "abcdef123456"


def test_docs_hidden_by_default(client):
    assert client.get("/api/docs").status_code == 404
