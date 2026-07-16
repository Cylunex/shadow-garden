from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from .. import auth
from ..db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 登录失败限流（仅配置了 Redis 时生效）：每 IP 十分钟内最多试 10 次
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW_SECONDS = 600
RATE_LIMIT_PREFIX = "garden:rl:login:"


class LoginIn(BaseModel):
    password: str


def _client_ip(request: Request) -> str:
    # nginx 反代会带 X-Real-IP；本地直连取对端地址
    return request.headers.get("x-real-ip") or (
        request.client.host if request.client else "unknown"
    )


@router.post("/login")
def login(body: LoginIn, request: Request, conn=Depends(get_db)):
    r = auth.get_redis()
    key = RATE_LIMIT_PREFIX + _client_ip(request)
    if r is not None:
        attempts = r.incr(key)
        if attempts == 1:
            r.expire(key, RATE_LIMIT_WINDOW_SECONDS)
        if attempts > RATE_LIMIT_MAX:
            raise HTTPException(429, "尝试次数太多，请十分钟后再试")

    if not auth.verify_password(body.password):
        raise HTTPException(401, "口令不对")

    if r is not None:
        r.delete(key)
    return auth.create_session(conn)


@router.post("/logout")
def logout(
    authorization: str = Header(default=""),
    conn=Depends(get_db),
):
    auth.destroy_session(conn, authorization)
    return {"ok": True}


@router.get("/me")
def me(is_admin: bool = Depends(auth.optional_admin)):
    return {"admin": is_admin}
