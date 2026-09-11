"""Unit tests for encrypted secret store and project-level credential isolation."""

from __future__ import annotations

import pytest

from agentlens.security.secrets import InMemorySecretStore


def test_in_memory_secret_store_lifecycle() -> None:
    store = InMemorySecretStore("test-master-secret-for-unit-tests")

    meta = store.store_secret(
        project_id="proj-alpha",
        name="openai-key",
        provider="openai",
        plaintext="sk-openai-test-key-12345",
    )
    assert meta.name == "openai-key"
    assert meta.provider == "openai"
    assert meta.project_id == "proj-alpha"

    # Retrieve decrypted plaintext
    secret_val = store.retrieve_secret("proj-alpha", "openai-key")
    assert secret_val == "sk-openai-test-key-12345"

    # List metadata (never includes plaintext)
    secrets_list = store.list_secrets("proj-alpha")
    assert len(secrets_list) == 1
    assert secrets_list[0].name == "openai-key"

    # Delete secret
    assert store.delete_secret("proj-alpha", "openai-key") is True
    assert store.retrieve_secret("proj-alpha", "openai-key") is None
    assert len(store.list_secrets("proj-alpha")) == 0


def test_secret_store_project_isolation() -> None:
    store = InMemorySecretStore("test-master-secret-for-unit-tests")

    store.store_secret(
        project_id="proj-1",
        name="shared-name",
        provider="anthropic",
        plaintext="sk-ant-proj1-key",
    )
    store.store_secret(
        project_id="proj-2",
        name="shared-name",
        provider="anthropic",
        plaintext="sk-ant-proj2-key",
    )

    # Verify proj-1 gets proj-1's key and not proj-2's
    assert store.retrieve_secret("proj-1", "shared-name") == "sk-ant-proj1-key"
    assert store.retrieve_secret("proj-2", "shared-name") == "sk-ant-proj2-key"

    # Verify listing is segregated
    p1_list = store.list_secrets("proj-1")
    p2_list = store.list_secrets("proj-2")
    assert len(p1_list) == 1
    assert len(p2_list) == 1


def test_empty_secret_raises() -> None:
    store = InMemorySecretStore("test-master-secret-for-unit-tests")
    with pytest.raises(ValueError, match="cannot be empty"):
        store.store_secret("proj-1", "key", "openai", "")
