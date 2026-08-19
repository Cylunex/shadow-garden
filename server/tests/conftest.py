"""测试基建。

默认零依赖：SQLite（每个测试独立临时目录）+ 数据库表会话。
设置以下环境变量后，同一套测试可整体切到生产同款后端：
    PG_TEST_URL=postgresql://user:pw@host/db_test   # 每个测试前清空该库
    REDIS_TEST_URL=redis://host:6379/15             # 每个测试前 FLUSHDB
"""
import os

import pytest
from fastapi.testclient import TestClient

TABLES = (
    "posts",
    "projects",
    "food",
    "trips",
    "moments",
    "about",
    "asset_files",
    "asset_uploads_pending",
    "sessions",
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GARDEN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GARDEN_AGENT_TOKEN", "test-agent-token")
    monkeypatch.setenv("GARDEN_ASSET_MODE", "local")
    secret_file = tmp_path / "oidc-client-secret"
    secret_file.write_text("test-client-secret", encoding="utf-8")
    monkeypatch.setenv("GARDEN_CANONICAL_URL", "http://testserver")
    monkeypatch.setenv("GARDEN_OIDC_ISSUER", "http://identity.test")
    monkeypatch.setenv("GARDEN_OIDC_CLIENT_ID", "shadow-garden")
    monkeypatch.setenv("GARDEN_OIDC_CLIENT_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("GARDEN_OIDC_REDIRECT_URI", "http://testserver/auth/callback")
    monkeypatch.setenv("GARDEN_OIDC_POST_LOGOUT_REDIRECT_URI", "http://testserver/")
    monkeypatch.setenv("GARDEN_OIDC_REQUIRED_GROUP", "garden-admins")
    monkeypatch.setenv("GARDEN_OIDC_SESSION_DB", str(tmp_path / "web_auth.db"))
    monkeypatch.setenv("GARDEN_OIDC_ALLOW_HTTP_FOR_TESTS", "1")

    pg_url = os.environ.get("PG_TEST_URL", "")
    if pg_url:
        monkeypatch.setenv("GARDEN_DB_URL", pg_url)
    else:
        monkeypatch.delenv("GARDEN_DB_URL", raising=False)

    redis_url = os.environ.get("REDIS_TEST_URL", "")
    if redis_url:
        monkeypatch.setenv("GARDEN_REDIS_URL", redis_url)
    else:
        monkeypatch.delenv("GARDEN_REDIS_URL", raising=False)

    if pg_url:
        # PG 测试库跨测试共享，先清干净再由 lifespan 重建
        from app import db

        conn = db.connect()
        for t in TABLES:
            conn.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
        conn.commit()
        conn.close()

    if redis_url:
        import redis

        redis.Redis.from_url(redis_url).flushdb()

    from app.main import app
    from app.oidc import reset_oidc_service

    reset_oidc_service()

    with TestClient(app) as c:
        yield c
    reset_oidc_service()


@pytest.fixture()
def admin_headers(client):
    from app.oidc import BrowserIdentity, SESSION_COOKIE, get_oidc_service

    identity = BrowserIdentity(
        shadow_user_id="test-admin",
        issuer="http://identity.test",
        subject="admin-subject",
        username="admin",
        display_name="Test Admin",
        email="admin@example.test",
        groups=("garden-admins",),
    )
    service = get_oidc_service()
    stored_identity = service.store.upsert_identity(
        {
            "iss": identity.issuer,
            "sub": identity.subject,
            "preferred_username": identity.username,
            "name": identity.display_name,
            "email": identity.email,
            "groups": list(identity.groups),
        }
    )
    session = service.store.create_session(stored_identity, ttl_seconds=300)
    return {
        "Cookie": f"{SESSION_COOKIE}={session.session_token}",
        "Origin": "http://testserver",
    }


@pytest.fixture()
def agent_headers():
    return {"Authorization": "Bearer test-agent-token"}
