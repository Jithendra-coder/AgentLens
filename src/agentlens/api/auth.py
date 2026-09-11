"""Storage-independent project-scoped Bearer API-key authentication."""

from __future__ import annotations

import hashlib
import hmac
import threading
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from agentlens.rbac.models import ALL_PERMISSIONS, Role, get_role_permissions
from agentlens.rbac.repository import RbacRepository


@dataclass(frozen=True, slots=True)
class AuthContext:
    """Safe authenticated metadata; raw secrets never leave the authenticator."""

    key_id: str
    project_id: str
    enabled: bool = True
    role: str = Role.PROJECT_ADMIN.value
    permissions: frozenset[str] = ALL_PERMISSIONS
    org_id: UUID | None = None


class ApiKeyAuthenticator(Protocol):
    """Storage-independent lookup boundary for Bearer API keys."""

    def authenticate(self, api_key: str) -> AuthContext | None:
        """Resolve a raw key to safe project-scoped metadata."""


@dataclass(frozen=True, slots=True)
class _KeyRecord:
    digest: bytes
    context: AuthContext


class InMemoryApiKeyAuthenticator:
    """Hashed in-memory API-key registry for integration tests and development."""

    def __init__(self) -> None:
        self._records: list[_KeyRecord] = []
        self._lock = threading.RLock()

    def register(
        self,
        *,
        api_key: str,
        key_id: str,
        project_id: str,
        enabled: bool = True,
        role: str = Role.PROJECT_ADMIN.value,
        permissions: frozenset[str] | None = None,
        org_id: UUID | None = None,
    ) -> None:
        """Register a high-entropy key as a one-way SHA-256 digest."""
        if not isinstance(api_key, str) or not api_key:
            raise ValueError("api_key must be a non-empty string")
        if not isinstance(key_id, str) or not key_id.strip():
            raise ValueError("key_id must be a non-empty string")
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("project_id must be a non-empty string")
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")

        assigned_perms = permissions if permissions is not None else get_role_permissions(role)
        record = _KeyRecord(
            digest=hashlib.sha256(api_key.encode("utf-8")).digest(),
            context=AuthContext(
                key_id=key_id,
                project_id=project_id,
                enabled=enabled,
                role=role,
                permissions=assigned_perms,
                org_id=org_id,
            ),
        )
        with self._lock:
            self._records = [
                existing for existing in self._records if existing.context.key_id != key_id
            ]
            self._records.append(record)

    def authenticate(self, api_key: str) -> AuthContext | None:
        """Return safe metadata for a valid enabled key, otherwise None."""
        if not isinstance(api_key, str) or not api_key or len(api_key) > 4096:
            return None
        digest = hashlib.sha256(api_key.encode("utf-8")).digest()
        with self._lock:
            for record in self._records:
                if hmac.compare_digest(record.digest, digest):
                    return record.context if record.context.enabled else None
        return None

    def __repr__(self) -> str:
        with self._lock:
            count = len(self._records)
        return f"InMemoryApiKeyAuthenticator(keys={count})"


class RbacApiKeyAuthenticator:
    """RBAC-backed API key authenticator with database lookup and fallback."""

    def __init__(
        self,
        repository: RbacRepository,
        fallback: ApiKeyAuthenticator | None = None,
    ) -> None:
        self.repository = repository
        self.fallback = fallback

    def authenticate(self, api_key: str) -> AuthContext | None:
        if not isinstance(api_key, str) or not api_key or len(api_key) > 4096:
            return None

        # Check repository
        try:
            info = self.repository.authenticate_key(api_key)
            if info is not None:
                return AuthContext(
                    key_id=info.key_id,
                    project_id=info.project_id,
                    enabled=info.is_active,
                    role=info.role,
                    permissions=info.permissions,
                    org_id=info.org_id,
                )
        except Exception:
            pass

        # Fallback to configured in-memory/static keys
        if self.fallback is not None:
            return self.fallback.authenticate(api_key)
        return None
