"""Integration tests for Enterprise Auth, JWT sessions, and Encrypted Secret Store."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.rbac import InMemoryRbacRepository, Role
from agentlens.security import InMemorySecretStore, InMemoryUserRepository

MASTER_KEY = "test-auth-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-default",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    secret_store = InMemorySecretStore("test-master-key-32-chars-long-12345")
    user_repo = InMemoryUserRepository()
    return create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=InMemoryTraceSink(),
        rbac_repository=rbac_repo,
        secret_store=secret_store,
        user_repository=user_repo,
    )


async def send_request(
    app,
    method: str,
    path: str,
    *,
    api_key: str | None = MASTER_KEY,
    jwt_token: str | None = None,
    json_body: object | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request_headers = dict(headers or {})
    if jwt_token is not None:
        request_headers["Authorization"] = f"Bearer {jwt_token}"
    elif api_key is not None:
        request_headers.setdefault("Authorization", f"Bearer {api_key}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, headers=request_headers, json=json_body)


def test_enterprise_auth_login_refresh_logout_lifecycle() -> None:
    app = make_test_app()

    async def run():
        # 1. Login
        login_res = await send_request(
            app,
            "POST",
            "/v1/auth/login",
            json_body={"email": "engineer@anthropic.com", "name": "Anthropic Engineer"},
            api_key=None,
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        access_token = login_data["access_token"]
        refresh_token = login_data["refresh_token"]
        assert access_token
        assert refresh_token.startswith("al_rt_")
        assert login_data["user"]["email"] == "engineer@anthropic.com"

        # 2. Get profile with JWT
        me_res = await send_request(app, "GET", "/v1/auth/me", jwt_token=access_token)
        assert me_res.status_code == 200
        me_data = me_res.json()
        assert me_data["email"] == "engineer@anthropic.com"
        assert me_data["role"] == "org_admin"

        # 3. Refresh Access Token
        refresh_res = await send_request(
            app,
            "POST",
            "/v1/auth/refresh",
            json_body={"refresh_token": refresh_token},
            api_key=None,
        )
        assert refresh_res.status_code == 200
        new_access_token = refresh_res.json()["access_token"]
        assert new_access_token

        # 4. Logout
        logout_res = await send_request(
            app,
            "POST",
            "/v1/auth/logout",
            json_body={"refresh_token": refresh_token},
            api_key=None,
        )
        assert logout_res.status_code == 200
        assert logout_res.json()["status"] == "logged_out"

        # 5. Subsequent refresh should fail (401)
        failed_refresh = await send_request(
            app,
            "POST",
            "/v1/auth/refresh",
            json_body={"refresh_token": refresh_token},
            api_key=None,
        )
        assert failed_refresh.status_code == 401
        assert failed_refresh.json()["error"]["code"] == "invalid_refresh_token"

    asyncio.run(run())


def test_encrypted_secret_store_api_lifecycle() -> None:
    app = make_test_app()

    async def run():
        # 1. Store encrypted OpenAI credential
        store_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-ai-labs/secrets",
            json_body={
                "name": "prod-openai-key",
                "provider": "openai",
                "secret_value": "sk-proj-super-secret-production-key-12345",
            },
        )
        assert store_res.status_code == 200
        store_data = store_res.json()
        assert store_data["name"] == "prod-openai-key"
        assert store_data["provider"] == "openai"
        assert store_data["is_encrypted"] is True
        # Plaintext must NEVER be present in the response
        assert "secret_value" not in store_data
        assert "ciphertext" not in store_data

        # 2. List secrets metadata
        list_res = await send_request(app, "GET", "/v1/projects/proj-ai-labs/secrets")
        assert list_res.status_code == 200
        secrets = list_res.json()["secrets"]
        assert len(secrets) == 1
        assert secrets[0]["name"] == "prod-openai-key"

        # 3. Delete secret
        del_res = await send_request(
            app,
            "DELETE",
            "/v1/projects/proj-ai-labs/secrets/prod-openai-key",
        )
        assert del_res.status_code == 200
        assert del_res.json()["deleted"] is True

        # 4. List after delete
        list_res2 = await send_request(app, "GET", "/v1/projects/proj-ai-labs/secrets")
        assert list_res2.status_code == 200
        assert len(list_res2.json()["secrets"]) == 0

    asyncio.run(run())
