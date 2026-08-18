"""Browser OIDC sessions and independent content-Agent Bearer authentication."""
import hmac
from typing import Optional

from fastapi import Header, HTTPException, Request

from .config import settings
from .oidc import BrowserIdentity, OIDCError, SESSION_COOKIE, get_oidc_service

_redis_clients = {}


def get_redis():
    url = settings.redis_url
    if not url:
        return None
    client = _redis_clients.get(url)
    if client is None:
        import redis

        client = redis.Redis.from_url(url, decode_responses=True)
        _redis_clients[url] = client
    return client


def browser_identity(request: Request) -> Optional[BrowserIdentity]:
    try:
        service = get_oidc_service()
    except OIDCError:
        return None
    record = service.store.authenticate_session(request.cookies.get(SESSION_COOKIE, ""))
    if not record or not record.identity.in_group(service.config.required_group):
        return None
    request.state.browser_identity = record.identity
    return record.identity


def require_admin(request: Request) -> BrowserIdentity:
    identity = browser_identity(request)
    if identity is None:
        raise HTTPException(401, "需要 Shadow Identity 管理员登录")
    _require_same_origin(request)
    return identity


def require_content_editor(
    request: Request,
    authorization: str = Header(default=""),
) -> Optional[BrowserIdentity]:
    identity = browser_identity(request)
    if identity is not None:
        _require_same_origin(request)
        return identity
    if not _agent_token_valid(_extract_token(authorization)):
        raise HTTPException(401, "需要内容编辑权限")
    return None


def optional_admin(request: Request) -> bool:
    return browser_identity(request) is not None


def optional_content_editor(
    request: Request,
    authorization: str = Header(default=""),
) -> bool:
    return browser_identity(request) is not None or _agent_token_valid(
        _extract_token(authorization)
    )


def _require_same_origin(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    expected = settings.canonical_url
    origin = request.headers.get("origin", "").rstrip("/")
    if not expected or not origin or not hmac.compare_digest(origin, expected):
        raise HTTPException(403, "请求来源校验失败")


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
