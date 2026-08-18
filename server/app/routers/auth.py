import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth import browser_identity, require_admin
from ..oidc import (
    OIDCError,
    SESSION_COOKIE,
    clear_session_cookie,
    get_oidc_service,
    sanitize_return_to,
    set_session_cookie,
)

router = APIRouter(tags=["auth"])
logger = logging.getLogger("shadow_garden.auth")


@router.get("/auth/login")
def login(return_to: str = "/admin/"):
    try:
        service = get_oidc_service()
        safe_return = sanitize_return_to(return_to)
        state, nonce, challenge = service.store.create_login_transaction(
            return_to=safe_return,
            ttl_seconds=service.config.transaction_ttl_seconds,
        )
        target = service.client.authorization_url(
            state=state,
            nonce=nonce,
            challenge=challenge,
        )
        return RedirectResponse(target, status_code=302)
    except OIDCError:
        return JSONResponse(
            {"ok": False, "error": "browser authentication is unavailable"},
            status_code=503,
        )


@router.get("/auth/callback")
def callback(state: str = "", code: str = "", error: str = ""):
    stage = "consume_state"
    try:
        service = get_oidc_service()
        transaction = service.store.consume_login_transaction(state)
        stage = "provider_response"
        if error:
            raise OIDCError("identity provider rejected login", reason="provider")
        stage = "exchange_code"
        token_response = service.client.exchange_code(
            code=code,
            verifier=transaction["code_verifier"],
        )
        stage = "verify_id_token"
        claims = service.client.verify_id_token(
            token_response["id_token"],
            nonce=transaction["nonce"],
        )
        stage = "complete_profile"
        claims = service.client.complete_profile_claims(claims, token_response)
        if service.config.required_group not in claims.get("groups", ()):
            return JSONResponse(
                {"ok": False, "error": "application access is not permitted"},
                status_code=403,
            )
        identity = service.store.upsert_identity(claims)
        session = service.store.create_session(
            identity,
            ttl_seconds=service.config.session_ttl_seconds,
        )
        response = RedirectResponse(
            sanitize_return_to(transaction["return_to"]),
            status_code=303,
        )
        set_session_cookie(response, session)
        response.headers["Cache-Control"] = "no-store"
        return response
    except OIDCError as exc:
        logger.warning("oidc_callback_rejected stage=%s reason=%s", stage, exc.reason)
        return JSONResponse(
            {"ok": False, "error": "OIDC callback validation failed"},
            status_code=400,
        )


@router.post("/auth/logout", dependencies=[Depends(require_admin)])
def logout(request: Request):
    service = get_oidc_service()
    service.store.revoke_session(request.cookies.get(SESSION_COOKIE, ""))
    response = JSONResponse({"ok": True})
    clear_session_cookie(response)
    return response


@router.post("/auth/logout/all", dependencies=[Depends(require_admin)])
def logout_all(request: Request):
    service = get_oidc_service()
    identity = request.state.browser_identity
    service.store.revoke_user_sessions(identity.shadow_user_id)
    response = RedirectResponse(service.client.global_logout_url(), status_code=303)
    clear_session_cookie(response)
    return response


@router.get("/api/auth/me")
def me(request: Request):
    identity = browser_identity(request)
    return {
        "admin": identity is not None,
        "display_name": identity.display_name if identity else "",
    }
