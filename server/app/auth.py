"""管理端鉴权：口令登录换会话 token（Bearer），token 存 SQLite 带过期。"""
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException

from .config import settings
from .db import get_db, now_iso


def verify_password(password: str) -> bool:
    configured = settings.admin_password
    if not configured:
        raise HTTPException(503, "服务端未配置 GARDEN_ADMIN_PASSWORD，管理功能不可用")
    return hmac.compare_digest(password.encode(), configured.encode())


def create_session(conn: sqlite3.Connection) -> dict:
    token = secrets.token_hex(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)
    expires_iso = expires.isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
        (token, now_iso(), expires_iso),
    )
    # 顺手清掉过期会话
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))
    return {"token": token, "expires_at": expires_iso}


def _token_valid(conn: sqlite3.Connection, token: str) -> bool:
    if not token:
        return False
    row = conn.execute(
        "SELECT expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    return bool(row and row["expires_at"] >= now_iso())


def _extract_token(authorization: str) -> str:
    if authorization.startswith("Bearer "):
        return authorization[len("Bearer "):].strip()
    return ""


def require_admin(
    authorization: str = Header(default=""),
    conn: sqlite3.Connection = Depends(get_db),
) -> None:
    if not _token_valid(conn, _extract_token(authorization)):
        raise HTTPException(401, "需要管理员登录")


def optional_admin(
    authorization: str = Header(default=""),
    conn: sqlite3.Connection = Depends(get_db),
) -> bool:
    return _token_valid(conn, _extract_token(authorization))


def destroy_session(conn: sqlite3.Connection, authorization: Optional[str]) -> None:
    token = _extract_token(authorization or "")
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
