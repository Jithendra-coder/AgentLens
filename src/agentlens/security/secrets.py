"""Encrypted model provider secret store implementation ."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, desc, select
from sqlalchemy.engine import Engine

from agentlens.security.crypto import (
    decrypt_payload,
    derive_encryption_key,
    encrypt_payload,
)
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import encrypted_secrets


@dataclass(frozen=True, slots=True)
class SecretMetadata:
    secret_id: UUID
    project_id: str
    name: str
    provider: str
    key_version: int
    created_at: datetime
    updated_at: datetime
    org_id: UUID | None = None


class SecretStore(Protocol):
    """Encrypted secret storage interface."""

    def store_secret(
        self,
        project_id: str,
        name: str,
        provider: str,
        plaintext: str,
        org_id: UUID | None = None,
    ) -> SecretMetadata: ...

    def retrieve_secret(self, project_id: str, name: str) -> str | None: ...

    def list_secrets(self, project_id: str) -> Sequence[SecretMetadata]: ...

    def delete_secret(self, project_id: str, name: str) -> bool: ...


class InMemorySecretStore:
    """In-memory encrypted secret store for tests and development."""

    def __init__(self, master_secret: str = "dev-insecure-master-key-32-chars-long") -> None:
        self._key = derive_encryption_key(master_secret)
        # (project_id, name) -> (SecretMetadata, ciphertext_hex, nonce_hex, tag_hex)
        self._records: dict[tuple[str, str], tuple[SecretMetadata, str, str, str]] = {}

    def store_secret(
        self,
        project_id: str,
        name: str,
        provider: str,
        plaintext: str,
        org_id: UUID | None = None,
    ) -> SecretMetadata:
        if not plaintext:
            raise ValueError("Secret plaintext cannot be empty")

        blob = encrypt_payload(self._key, plaintext)
        now = datetime.now(UTC)
        meta = SecretMetadata(
            secret_id=uuid4(),
            project_id=project_id,
            name=name,
            provider=provider,
            key_version=1,
            created_at=now,
            updated_at=now,
            org_id=org_id,
        )
        self._records[(project_id, name)] = (meta, blob.ciphertext, blob.nonce, blob.tag)
        return meta

    def retrieve_secret(self, project_id: str, name: str) -> str | None:
        entry = self._records.get((project_id, name))
        if entry is None:
            return None
        _, ciphertext, nonce, tag = entry
        return decrypt_payload(self._key, ciphertext, nonce, tag)

    def list_secrets(self, project_id: str) -> Sequence[SecretMetadata]:
        return [meta for (p, _), (meta, _, _, _) in self._records.items() if p == project_id]

    def delete_secret(self, project_id: str, name: str) -> bool:
        if (project_id, name) in self._records:
            del self._records[(project_id, name)]
            return True
        return False


class PostgresSecretStore:
    """PostgreSQL-backed AES-256-GCM encrypted secret store."""

    def __init__(
        self,
        config: DatabaseConfig,
        master_secret: str,
        *,
        engine: Engine | None = None,
    ) -> None:
        self.engine = engine or create_engine(
            config.sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
        )
        self._key = derive_encryption_key(master_secret)

    def store_secret(
        self,
        project_id: str,
        name: str,
        provider: str,
        plaintext: str,
        org_id: UUID | None = None,
    ) -> SecretMetadata:
        if not plaintext:
            raise ValueError("Secret plaintext cannot be empty")

        blob = encrypt_payload(self._key, plaintext)
        secret_id = uuid4()
        now = datetime.now(UTC)

        with self.engine.begin() as conn:
            # Delete existing if any for idempotency
            conn.execute(
                encrypted_secrets.delete().where(
                    and_(
                        encrypted_secrets.c.project_id == project_id,
                        encrypted_secrets.c.name == name,
                    )
                )
            )
            conn.execute(
                encrypted_secrets.insert().values(
                    secret_id=secret_id,
                    project_id=project_id,
                    org_id=org_id,
                    name=name,
                    provider=provider,
                    ciphertext=blob.ciphertext,
                    nonce=blob.nonce,
                    tag=blob.tag,
                    key_version=1,
                    created_at=now,
                    updated_at=now,
                )
            )

        return SecretMetadata(
            secret_id=secret_id,
            project_id=project_id,
            name=name,
            provider=provider,
            key_version=1,
            created_at=now,
            updated_at=now,
            org_id=org_id,
        )

    def retrieve_secret(self, project_id: str, name: str) -> str | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(encrypted_secrets).where(
                    and_(
                        encrypted_secrets.c.project_id == project_id,
                        encrypted_secrets.c.name == name,
                    )
                )
            ).mappings().one_or_none()
            if row is None:
                return None
            return decrypt_payload(
                self._key,
                str(row["ciphertext"]),
                str(row["nonce"]),
                str(row["tag"]),
            )

    def list_secrets(self, project_id: str) -> Sequence[SecretMetadata]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(encrypted_secrets)
                .where(encrypted_secrets.c.project_id == project_id)
                .order_by(desc(encrypted_secrets.c.created_at))
            ).mappings().all()
            return [
                SecretMetadata(
                    secret_id=cast(UUID, r["secret_id"]),
                    project_id=str(r["project_id"]),
                    name=str(r["name"]),
                    provider=str(r["provider"]),
                    key_version=int(r["key_version"]),
                    created_at=cast(datetime, r["created_at"]),
                    updated_at=cast(datetime, r["updated_at"]),
                    org_id=cast(UUID | None, r["org_id"]),
                )
                for r in rows
            ]

    def delete_secret(self, project_id: str, name: str) -> bool:
        with self.engine.begin() as conn:
            res = conn.execute(
                encrypted_secrets.delete().where(
                    and_(
                        encrypted_secrets.c.project_id == project_id,
                        encrypted_secrets.c.name == name,
                    )
                )
            )
            return bool(int(getattr(res, "rowcount", 0) or 0) > 0)
