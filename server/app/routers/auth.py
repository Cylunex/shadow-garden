import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from .. import auth
from ..db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str


@router.post("/login")
def login(body: LoginIn, conn: sqlite3.Connection = Depends(get_db)):
    if not auth.verify_password(body.password):
        raise HTTPException(401, "口令不对")
    return auth.create_session(conn)


@router.post("/logout")
def logout(
    authorization: str = Header(default=""),
    conn: sqlite3.Connection = Depends(get_db),
):
    auth.destroy_session(conn, authorization)
    return {"ok": True}


@router.get("/me")
def me(is_admin: bool = Depends(auth.optional_admin)):
    return {"admin": is_admin}
