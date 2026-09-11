"""Unit tests for cryptographic primitives and AES-256-GCM authenticated encryption."""

from __future__ import annotations

import pytest

from agentlens.exceptions import SecurityError
from agentlens.security.crypto import (
    decrypt_payload,
    derive_encryption_key,
    encrypt_payload,
)


def test_derive_encryption_key() -> None:
    key1 = derive_encryption_key("my-secret-passphrase")
    key2 = derive_encryption_key("my-secret-passphrase")
    assert key1 == key2
    assert len(key1) == 32

    key3 = derive_encryption_key("different-passphrase")
    assert key1 != key3

    with pytest.raises(ValueError, match="master_secret must not be empty"):
        derive_encryption_key("")


def test_aes_256_gcm_encryption_roundtrip() -> None:
    key = derive_encryption_key("sample-master-key")
    plaintext = "sk-proj-openai-api-key-123456789"

    blob = encrypt_payload(key, plaintext)
    assert blob.ciphertext
    assert blob.nonce
    assert blob.tag
    assert len(blob.nonce) == 24  # 12 bytes = 24 hex characters
    assert len(blob.tag) == 32  # 16 bytes = 32 hex characters

    decrypted = decrypt_payload(key, blob.ciphertext, blob.nonce, blob.tag)
    assert decrypted == plaintext


def test_aes_256_gcm_tamper_detection() -> None:
    key = derive_encryption_key("sample-master-key")
    plaintext = "super-secret-token"

    blob = encrypt_payload(key, plaintext)

    # Corrupt the ciphertext
    tampered_cipher = ("0" if blob.ciphertext[0] != "0" else "1") + blob.ciphertext[1:]
    with pytest.raises(SecurityError, match="authentication tag verification failed"):
        decrypt_payload(key, tampered_cipher, blob.nonce, blob.tag)

    # Corrupt the tag
    tampered_tag = ("0" if blob.tag[0] != "0" else "1") + blob.tag[1:]
    with pytest.raises(SecurityError, match="authentication tag verification failed"):
        decrypt_payload(key, blob.ciphertext, blob.nonce, tampered_tag)


def test_invalid_key_length() -> None:
    with pytest.raises(ValueError, match="requires a 32-byte key"):
        encrypt_payload(b"short-key", "data")

    with pytest.raises(ValueError, match="requires a 32-byte key"):
        decrypt_payload(b"short-key", "00", "00", "00")
