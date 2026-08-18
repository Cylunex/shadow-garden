import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import oidc


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("request failed")


class FakeOIDCHTTP:
    def __init__(self, issuer, jwk, private_key):
        self.issuer = issuer
        self.jwk = jwk
        self.private_key = private_key
        self.expected_nonce = ""
        self.claim_overrides = {}
        self.userinfo_payload = {
            "sub": "subject-1",
            "preferred_username": "garden-owner",
            "name": "Garden Owner",
            "email": "owner@example.test",
            "groups": ["garden-admins"],
        }

    def get(self, url, **_kwargs):
        if url.endswith("/.well-known/openid-configuration"):
            return FakeResponse(
                {
                    "issuer": self.issuer,
                    "authorization_endpoint": self.issuer + "/authorize",
                    "token_endpoint": self.issuer + "/token",
                    "userinfo_endpoint": self.issuer + "/userinfo",
                    "jwks_uri": self.issuer + "/jwks",
                    "end_session_endpoint": self.issuer + "/logout",
                }
            )
        if url.endswith("/jwks"):
            return FakeResponse({"keys": [self.jwk]})
        if url.endswith("/userinfo"):
            return FakeResponse(self.userinfo_payload)
        return FakeResponse({}, 404)

    def post(self, _url, *, data, auth, **_kwargs):
        assert auth[0] == "shadow-garden"
        assert len(data["code_verifier"]) >= 43
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "sub": "subject-1",
            "aud": "shadow-garden",
            "iat": now,
            "exp": now + 300,
            "nonce": self.expected_nonce,
            "preferred_username": "garden-owner",
            "name": "Garden Owner",
            "groups": ["garden-admins"],
        }
        claims.update(self.claim_overrides)
        token = jwt.encode(
            claims,
            self.private_key,
            algorithm="RS256",
            headers={"kid": "garden-key"},
        )
        return FakeResponse({"id_token": token, "access_token": "discard-me"})


def jwk_for(private_key):
    value = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    value.update({"kid": "garden-key", "use": "sig", "alg": "RS256"})
    return value


@pytest.fixture()
def oidc_http(client):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    fake_http = FakeOIDCHTTP("http://identity.test", jwk_for(private_key), private_key)
    service = oidc.OIDCService(oidc.OIDCConfig.from_settings(), http=fake_http)
    oidc._service = service
    return fake_http, service, private_key


def test_pkce_state_is_one_time_and_return_path_is_sanitized(oidc_http):
    _fake_http, service, _private_key = oidc_http
    state, nonce, challenge = service.store.create_login_transaction(
        return_to="/admin/?tab=posts",
        ttl_seconds=60,
    )
    transaction = service.store.consume_login_transaction(state)
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(transaction["code_verifier"].encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert challenge == expected
    assert transaction["nonce"] == nonce
    assert transaction["return_to"] == "/admin/?tab=posts"
    with pytest.raises(oidc.OIDCError):
        service.store.consume_login_transaction(state)
    assert oidc.sanitize_return_to("https://evil.example/steal") == "/admin/"
    assert oidc.sanitize_return_to("//evil.example/steal") == "/admin/"


def test_oidc_login_callback_sets_strict_cookie(client, oidc_http):
    fake_http, _service, _private_key = oidc_http
    start = client.get(
        "/auth/login",
        params={"return_to": "/admin/?tab=posts"},
        follow_redirects=False,
    )
    assert start.status_code == 302
    query = parse_qs(urlsplit(start.headers["location"]).query)
    fake_http.expected_nonce = query["nonce"][0]
    assert query["code_challenge_method"] == ["S256"]

    callback = client.get(
        "/auth/callback",
        params={"state": query["state"][0], "code": "example-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "/admin/?tab=posts"
    cookie = callback.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Domain=" not in cookie
    session_cookie = cookie.split(";", 1)[0]
    me = client.get("/api/auth/me", headers={"Cookie": session_cookie})
    assert me.json() == {"admin": True, "display_name": "Garden Owner"}


def test_oidc_group_gate_rejects_unrelated_users(client, oidc_http):
    fake_http, _service, _private_key = oidc_http
    fake_http.claim_overrides = {"groups": ["unrelated-users"]}
    start = client.get("/auth/login", follow_redirects=False)
    query = parse_qs(urlsplit(start.headers["location"]).query)
    fake_http.expected_nonce = query["nonce"][0]
    callback = client.get(
        "/auth/callback",
        params={"state": query["state"][0], "code": "example-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 403
    assert oidc.SESSION_COOKIE not in callback.cookies


def test_id_token_rejects_wrong_audience_and_nonce(oidc_http):
    _fake_http, service, private_key = oidc_http
    now = int(time.time())

    def encode(**overrides):
        claims = {
            "iss": "http://identity.test",
            "sub": "subject-1",
            "aud": "shadow-garden",
            "iat": now,
            "exp": now + 300,
            "nonce": "expected",
            "groups": ["garden-admins"],
        }
        claims.update(overrides)
        return jwt.encode(
            claims,
            private_key,
            algorithm="RS256",
            headers={"kid": "garden-key"},
        )

    assert service.client.verify_id_token(encode(), nonce="expected")["sub"] == "subject-1"
    with pytest.raises(oidc.OIDCError) as audience_error:
        service.client.verify_id_token(encode(aud="wrong-client"), nonce="expected")
    assert audience_error.value.reason == "audience"
    with pytest.raises(oidc.OIDCError) as nonce_error:
        service.client.verify_id_token(encode(nonce="wrong"), nonce="expected")
    assert nonce_error.value.reason == "nonce"
