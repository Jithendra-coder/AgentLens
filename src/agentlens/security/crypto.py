"""Cryptographic primitives: AES-256-GCM authenticated encryption and key derivation."""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from agentlens.security.errors import SecurityError

DEFAULT_SALT = b"agentlens-secrets-master-salt-v1"


def derive_encryption_key(
    master_secret: str,
    salt: bytes = DEFAULT_SALT,
    iterations: int = 100_000,
) -> bytes:
    """Derive a 256-bit (32 bytes) encryption key from a master passphrase using PBKDF2."""
    if not master_secret:
        raise ValueError("master_secret must not be empty")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(master_secret.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class EncryptedBlob:
    ciphertext: str  # Hex encoded
    nonce: str  # Hex encoded
    tag: str  # Hex encoded


def encrypt_payload(
    key: bytes,
    plaintext: str,
    associated_data: bytes | None = None,
) -> EncryptedBlob:
    """Encrypt a plaintext string using AES-256-GCM with a random 96-bit nonce."""
    if len(key) != 32:
        raise ValueError("AES-256 requires a 32-byte key")

    nonce = os.urandom(12)  # 96 bits recommended for AES-GCM
    aesgcm = AESGCM(key)
    raw_ciphertext_and_tag = aesgcm.encrypt(
        nonce,
        plaintext.encode("utf-8"),
        associated_data,
    )
    # The last 16 bytes of AESGCM output in Python cryptography is the authentication tag
    tag = raw_ciphertext_and_tag[-16:]
    ciphertext = raw_ciphertext_and_tag[:-16]

    return EncryptedBlob(
        ciphertext=ciphertext.hex(),
        nonce=nonce.hex(),
        tag=tag.hex(),
    )


def decrypt_payload(
    key: bytes,
    ciphertext_hex: str,
    nonce_hex: str,
    tag_hex: str,
    associated_data: bytes | None = None,
) -> str:
    """Decrypt and authenticate an AES-256-GCM ciphertext."""
    if len(key) != 32:
        raise ValueError("AES-256 requires a 32-byte key")

    try:
        nonce = bytes.fromhex(nonce_hex)
        ciphertext = bytes.fromhex(ciphertext_hex)
        tag = bytes.fromhex(tag_hex)
    except ValueError as e:
        raise SecurityError(f"Malformed hexadecimal secret data: {e}") from e

    combined = ciphertext + tag
    aesgcm = AESGCM(key)
    try:
        decrypted_bytes = aesgcm.decrypt(nonce, combined, associated_data)
        return decrypted_bytes.decode("utf-8")
    except InvalidTag as e:
        raise SecurityError(
            "Secret decryption failed: authentication tag verification failed. "
            "Data may have been tampered with or corrupted."
        ) from e
