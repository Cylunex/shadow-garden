"""测试基建。

默认零依赖：SQLite（每个测试独立临时目录）+ 数据库表会话。
设置以下环境变量后，同一套测试可整体切到生产同款后端：
    PG_TEST_URL=postgresql://user:pw@host/db_test   # 每个测试前清空该库
    REDIS_TEST_URL=redis://host:6379/15             # 每个测试前 FLUSHDB
"""
import os

import pytest
from fastapi.testclient import TestClient

TABLES = ("posts", "projects", "food", "trips", "moments", "about", "sessions")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GARDEN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GARDEN_ADMIN_PASSWORD", "test-pass")
    monkeypatch.setenv("GARDEN_AGENT_TOKEN", "test-agent-token")

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

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"password": "test-pass"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture()
def agent_headers():
    return {"Authorization": "Bearer test-agent-token"}
