def test_liveness_is_stateless(client, monkeypatch):
    monkeypatch.setattr("app.main.connect", lambda: (_ for _ in ()).throw(RuntimeError()))
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readiness_checks_dependencies(client):
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
