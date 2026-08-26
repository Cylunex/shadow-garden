"""Shadow Agent authentication for Garden's machine API."""

from __future__ import annotations

import hmac
from pathlib import Path

from fastapi import HTTPException
from shadow_sdk.agent import AgentAuthenticator, AgentAuthError, AgentIdentity

from .config import settings

_authenticator: AgentAuthenticator | None = None
_authenticator_key: tuple[str, str] | None = None

_LEGACY_SCOPES = frozenset(
    {
        "garden.summary.read",
        "garden.posts.draft",
        "garden.posts.review",
        "garden.posts.publish",
    }
)


def require_agent(authorization: str, *, scope: str) -> AgentIdentity:
    registry = settings.agent_registry_path.strip()
    secrets_dir = settings.agent_secrets_dir.strip()
    try:
        if registry or secrets_dir:
            if not registry or not secrets_dir:
                raise AgentAuthError("agent registry and secrets directory must both be configured")
            identity = _registry_authenticator(registry, secrets_dir).authenticate(authorization)
        else:
            identity = _legacy_identity(authorization)
        identity.require_scope(scope)
        return identity
    except (AgentAuthError, OSError, ValueError) as exc:
        raise HTTPException(401, str(exc)) from exc


def _registry_authenticator(registry: str, secrets_dir: str) -> AgentAuthenticator:
    global _authenticator, _authenticator_key
    key = (str(Path(registry).expanduser()), str(Path(secrets_dir).expanduser()))
    if _authenticator is None or _authenticator_key != key:
        _authenticator = AgentAuthenticator(
            key[0],
            secrets_dir=key[1],
            audience="garden",
        )
        _authenticator_key = key
    return _authenticator


def _legacy_identity(authorization: str) -> AgentIdentity:
    scheme, separator, token = authorization.partition(" ")
    configured = settings.agent_token
    if (
        not separator
        or scheme.lower() != "bearer"
        or not configured
        or not token
        or not hmac.compare_digest(token.encode(), configured.encode())
    ):
        raise AgentAuthError("valid Garden Agent Bearer token required")
    return AgentIdentity(
        agent_id="garden-content-agent",
        owner_app="garden",
        audience="garden",
        scopes=_LEGACY_SCOPES,
        capabilities=_LEGACY_SCOPES,
    )
