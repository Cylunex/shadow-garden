"""管理端鉴权：口令登录换会话 token（Bearer）。

会话存储：配置 GARDEN_REDIS_URL 时用 Redis（原生 TTL 过期），
否则落在数据库 sessions 表（带过期时间，登录时顺手清理）。
"""
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException

from .config import settings
from .db import get_db, now_iso

SESSION_PREFIX = "garden:session:"

_redis_clients = {}


def get_redis():
    """按 URL 缓存的 Redis 客户端；未配置返回 None。"""
    url = settings.redis_url
    if not url:
        return None
    client = _redis_clients.get(url)
    if client is None:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        _redis_clients[url] = client
    return client


def verify_password(password: str) -> bool:
    configured = settings.admin_password
    if not configured:
        raise HTTPException(503, "服务端未配置 GARDEN_ADMIN_PASSWORD，管理功能不可用")
    return hmac.compare_digest(password.encode(), configured.encode())


def create_session(conn) -> dict:
    token = secrets.token_hex(32)
    ttl = timedelta(hours=settings.session_ttl_hours)
    expires_iso = (datetime.now(timezone.utc) + ttl).isoformat(timespec="seconds")

    r = get_redis()
    if r is not None:
        r.setex(SESSION_PREFIX + token, ttl, "1")
    else:
        conn.execute(
            "INSERT INTO sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
            (token, now_iso(), expires_iso),
        )
        # 顺手清掉过期会话
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
    return {"token": token, "expires_at": expires_iso}


def _token_valid(conn, token: str) -> bool:
    if not token:
        return False
    r = get_redis()
    if r is not None:
        return bool(r.exists(SESSION_PREFIX + token))
    row = conn.execute(
        "SELECT expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    return bool(row and row["expires_at"] >= now_iso())


def _extract_token(authorization: str) -> str:
    if authorization.startswith("Bearer "):
        return authorization[len("Bearer "):].strip()
    return ""


def _agent_token_valid(token: str) -> bool:
    configured = settings.agent_token
    return bool(
        configured
        and token
        and hmac.compare_digest(token.encode(), configured.encode())
    )


def require_admin(
    authorization: str = Header(default=""),
    conn=Depends(get_db),
) -> None:
    if not _token_valid(conn, _extract_token(authorization)):
        raise HTTPException(401, "需要管理员登录")


def require_content_editor(
    authorization: str = Header(default=""),
    conn=Depends(get_db),
) -> None:
    token = _extract_token(authorization)
    if not (_token_valid(conn, token) or _agent_token_valid(token)):
        raise HTTPException(401, "需要内容编辑权限")


def optional_admin(
    authorization: str = Header(default=""),
    conn=Depends(get_db),
) -> bool:
    return _token_valid(conn, _extract_token(authorization))


def optional_content_editor(
    authorization: str = Header(default=""),
    conn=Depends(get_db),
) -> bool:
    token = _extract_token(authorization)
    return _token_valid(conn, token) or _agent_token_valid(token)


def destroy_session(conn, authorization: Optional[str]) -> None:
    token = _extract_token(authorization or "")
    if not token:
        return
    r = get_redis()
    if r is not None:
        r.delete(SESSION_PREFIX + token)
    else:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
