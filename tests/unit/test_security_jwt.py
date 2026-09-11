"""Unit tests for JWT token generation, signature verification, and session management."""

from __future__ import annotations

import time

import pytest

from agentlens.exceptions import SecurityError
from agentlens.security.jwt_tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_access_token,
)
from agentlens.security.users import InMemoryUserRepository


def test_jwt_access_token_creation_and_verification() -> None:
    secret = "my-secret-key-32-chars-long-abcde"
    token = create_access_token(
        user_id="user-uuid-123",
        email="test@agentlens.ai",
        secret_key=secret,
        roles=["org_admin", "project_admin"],
        expires_in_seconds=60,
    )

    claims = verify_access_token(token, secret)
    assert claims["sub"] == "user-uuid-123"
    assert claims["email"] == "test@agentlens.ai"
    assert "org_admin" in claims["roles"]
    assert claims["iss"] == "agentlens"


def test_jwt_tamper_signature_rejection() -> None:
    secret = "my-secret-key-32-chars-long-abcde"
    token = create_access_token(
        user_id="user-uuid-123",
        email="test@agentlens.ai",
        secret_key=secret,
        expires_in_seconds=60,
    )

    # Tamper with header/payload or signature
    parts = token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.badsignature"
    with pytest.raises(SecurityError, match="signature verification failed"):
        verify_access_token(tampered_token, secret)


def test_jwt_expiration() -> None:
    secret = "my-secret-key-32-chars-long-abcde"
    token = create_access_token(
        user_id="user-uuid-123",
        email="test@agentlens.ai",
        secret_key=secret,
        expires_in_seconds=1,
    )

    time.sleep(1.2)
    with pytest.raises(SecurityError, match="Token has expired"):
        verify_access_token(token, secret)


def test_refresh_token_lifecycle_and_user_repository() -> None:
    raw_token, token_hash = generate_refresh_token()
    assert raw_token.startswith("al_rt_")
    assert hash_refresh_token(raw_token) == token_hash

    repo = InMemoryUserRepository()
    user = repo.get_or_create_user("alice@agentlens.ai", "Alice")
    assert user.email == "alice@agentlens.ai"

    session = repo.create_session(user.user_id, token_hash, user_agent="Mozilla/5.0")
    assert session.is_valid is True

    fetched_session = repo.get_session(token_hash)
    assert fetched_session is not None
    assert fetched_session.session_id == session.session_id

    # Revoke session
    assert repo.revoke_session(session.session_id) is True
    assert repo.get_session(token_hash) is None
