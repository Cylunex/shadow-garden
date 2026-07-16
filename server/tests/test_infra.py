"""依赖 Redis 的能力：登录失败限流（无 REDIS_TEST_URL 时跳过）。

会话的 Redis 路径不单独测——设置 REDIS_TEST_URL 跑全套时，
所有登录/登出/鉴权用例走的就是 Redis。
"""
import os

import pytest

needs_redis = pytest.mark.skipif(
    not os.environ.get("REDIS_TEST_URL"), reason="需要 REDIS_TEST_URL"
)


@needs_redis
def test_login_rate_limit(client):
    for _ in range(10):
        assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    # 第 11 次起被限流，连正确口令也进不来
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 429
    assert client.post("/api/auth/login", json={"password": "test-pass"}).status_code == 429


@needs_redis
def test_rate_limit_resets_after_success(client):
    for _ in range(3):
        client.post("/api/auth/login", json={"password": "wrong"})
    # 成功登录清零计数
    assert client.post("/api/auth/login", json={"password": "test-pass"}).status_code == 200
    for _ in range(9):
        client.post("/api/auth/login", json={"password": "wrong"})
    assert client.post("/api/auth/login", json={"password": "test-pass"}).status_code == 200
