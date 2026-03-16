"""Tests for JWT auth utilities — no DB, no network."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from schoolai.api.auth import _ALGORITHM, create_access_token


# Use a fixed secret for tests
_SECRET = "test-secret-key-32chars-minimum!!"


def _decode(token: str) -> dict:
    return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])


# ── create_access_token ───────────────────────────────────────────────────────

def test_token_contains_sub(monkeypatch):
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_secret_key", _SECRET)
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_expire_hours", 24)
    token = create_access_token(123456789, "teacher")
    payload = _decode(token)
    assert payload["sub"] == "123456789"


def test_token_contains_role(monkeypatch):
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_secret_key", _SECRET)
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_expire_hours", 24)
    for role in ("teacher", "admin", "superadmin", "secretaria"):
        token = create_access_token(1, role)
        assert _decode(token)["role"] == role


def test_token_exp_within_24h(monkeypatch):
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_secret_key", _SECRET)
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_expire_hours", 24)
    token = create_access_token(1, "teacher")
    payload = _decode(token)
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    now = datetime.now(timezone.utc)
    assert timedelta(hours=23) < (exp - now) <= timedelta(hours=24, minutes=1)


def test_token_is_string(monkeypatch):
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_secret_key", _SECRET)
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_expire_hours", 1)
    assert isinstance(create_access_token(1, "teacher"), str)


# ── get_current_user (via FastAPI TestClient) ─────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    """TestClient with JWT secret configured. DB errors surface as 500, not raised."""
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_secret_key", _SECRET)
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_expire_hours", 24)
    from fastapi.testclient import TestClient
    from schoolai.api.main import app
    return TestClient(app, raise_server_exceptions=False)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_protected_without_token(client):
    r = client.get("/homework/")
    assert r.status_code in (401, 403)   # HTTPBearer returns 401 or 403 without credentials


def test_protected_with_invalid_token(client):
    r = client.get("/homework/", headers=_bearer("bad.token.here"))
    assert r.status_code == 401


def test_protected_with_expired_token(client, monkeypatch):
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_secret_key", _SECRET)
    # Build an already-expired token manually
    payload = {
        "sub": "1",
        "role": "teacher",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
    }
    expired = jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)
    r = client.get("/homework/", headers=_bearer(expired))
    assert r.status_code == 401
    assert "expirado" in r.json()["detail"].lower()


def test_valid_token_passes_auth(client, monkeypatch):
    """Valid JWT should not cause a 401/403 (may get 500 from DB, that's OK here)."""
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_secret_key", _SECRET)
    monkeypatch.setattr("schoolai.api.auth.settings.jwt_expire_hours", 24)
    token = create_access_token(999, "teacher")
    r = client.get("/homework/", headers=_bearer(token))
    # 401/403 = auth failed; anything else = auth passed (may fail at DB layer)
    assert r.status_code not in (401, 403)


def test_public_routes_no_auth_needed(client):
    """Catalog endpoints should not require auth."""
    for path in ("/grades/", "/subjects/"):
        r = client.get(path)
        assert r.status_code not in (401, 403), f"{path} should be public"
