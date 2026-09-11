"""AgentLens Security Subsystem.

AES-256-GCM encrypted secrets, JWT authentication, and user sessions.
"""

from agentlens.security.crypto import (
    EncryptedBlob,
    decrypt_payload,
    derive_encryption_key,
    encrypt_payload,
)
from agentlens.security.jwt_tokens import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_access_token,
)
from agentlens.security.secrets import (
    InMemorySecretStore,
    PostgresSecretStore,
    SecretMetadata,
    SecretStore,
)
from agentlens.security.users import (
    InMemoryUserRepository,
    PostgresUserRepository,
    User,
    UserRepository,
    UserSession,
)

__all__ = (
    "EncryptedBlob",
    "InMemorySecretStore",
    "InMemoryUserRepository",
    "PostgresSecretStore",
    "PostgresUserRepository",
    "SecretMetadata",
    "SecretStore",
    "User",
    "UserRepository",
    "UserSession",
    "create_access_token",
    "decrypt_payload",
    "derive_encryption_key",
    "encrypt_payload",
    "generate_refresh_token",
    "hash_refresh_token",
    "verify_access_token",
)
