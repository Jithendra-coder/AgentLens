"""RFC 7519 JSON Web Token (JWT) encode/decode with HMAC-SHA256 signature verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from agentlens.security.errors import SecurityError


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4)) if len(data) % 4 != 0 else ""
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def create_access_token(
    user_id: str,
    email: str,
    secret_key: str,
    *,
    roles: list[str] | None = None,
    expires_in_seconds: int = 3600,
    issuer: str = "agentlens",
) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expires_in_seconds)

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "roles": roles or ["project_viewer"],
        "iss": issuer,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    header_b64 = _base64url_encode(header_bytes)
    payload_b64 = _base64url_encode(payload_bytes)

    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_access_token(
    token: str,
    secret_key: str,
    *,
    issuer: str = "agentlens",
) -> dict[str, Any]:
    """Verify a signed JWT access token and return claims."""
    if not token or not isinstance(token, str):
        raise SecurityError("Invalid token format")

    parts = token.split(".")
    if len(parts) != 3:
        raise SecurityError("Malformed JWT structure")

    header_b64, payload_b64, sig_b64 = parts

    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected_sig = hmac.new(secret_key.encode("utf-8"), signing_input, hashlib.sha256).digest()

    try:
        actual_sig = _base64url_decode(sig_b64)
    except Exception as e:
        raise SecurityError("Invalid token signature encoding") from e

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise SecurityError("Token signature verification failed")

    try:
        payload_json = _base64url_decode(payload_b64)
        payload = json.loads(payload_json.decode("utf-8"))
    except Exception as e:
        raise SecurityError("Invalid token payload") from e

    # Validate claims
    if payload.get("iss") != issuer:
        raise SecurityError(f"Invalid token issuer: expected {issuer}")

    exp = payload.get("exp")
    if exp is None or not isinstance(exp, int):
        raise SecurityError("Token missing expiration claim")

    now_ts = int(datetime.now(UTC).timestamp())
    if now_ts >= exp:
        raise SecurityError("Token has expired")

    return cast(dict[str, Any], payload)


def generate_refresh_token() -> tuple[str, str]:
    """Generate a high-entropy refresh token and its SHA-256 hash for database storage."""
    raw_token = f"al_rt_{secrets.token_urlsafe(48)}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    return raw_token, token_hash


def hash_refresh_token(raw_token: str) -> str:
    """Hash a raw refresh token with SHA-256."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
