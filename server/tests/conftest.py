import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GARDEN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GARDEN_ADMIN_PASSWORD", "test-pass")
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"password": "test-pass"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}
