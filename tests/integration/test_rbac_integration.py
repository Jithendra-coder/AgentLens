"""Integration tests  multi-tenant isolation, RBAC routes, and scoped API key lifecycle."""

from __future__ import annotations

import asyncio

import httpx

from agentlens.api import InMemoryApiKeyAuthenticator, create_app
from agentlens.api.config import GatewayConfig
from agentlens.api.sink import InMemoryTraceSink
from agentlens.rbac import InMemoryRbacRepository, Role

MASTER_KEY = "test-rbac-master-key"


def make_test_app():
    authenticator = InMemoryApiKeyAuthenticator()
    authenticator.register(
        api_key=MASTER_KEY,
        key_id="master-key-1",
        project_id="proj-default",
        role=Role.ORG_ADMIN.value,
    )
    rbac_repo = InMemoryRbacRepository()
    return create_app(
        config=GatewayConfig(),
        authenticator=authenticator,
        sink=InMemoryTraceSink(),
        rbac_repository=rbac_repo,
    )


async def send_request(
    app,
    method: str,
    path: str,
    *,
    api_key: str | None = MASTER_KEY,
    json_body: object | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    request_headers = dict(headers or {})
    if api_key is not None:
        request_headers.setdefault("Authorization", f"Bearer {api_key}")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        return await client.request(method, path, headers=request_headers, json=json_body)


def test_organizations_and_projects_lifecycle() -> None:
    app = make_test_app()

    async def run():
        # Create Org
        org_res = await send_request(
            app,
            "POST",
            "/v1/organizations",
            json_body={"name": "Tesla AI", "slug": "tesla-ai"},
        )
        assert org_res.status_code == 200
        org_data = org_res.json()
        org_id = org_data["org_id"]

        # List Orgs
        orgs_list = await send_request(app, "GET", "/v1/organizations")
        assert orgs_list.status_code == 200
        assert len(orgs_list.json()["organizations"]) == 1

        # Create Project in Org
        proj_res = await send_request(
            app,
            "POST",
            f"/v1/organizations/{org_id}/projects",
            json_body={
                "project_id": "proj-fsd",
                "name": "FSD Autonomous",
                "slug": "fsd-autonomous",
            },
        )
        assert proj_res.status_code == 200
        proj_data = proj_res.json()
        assert proj_data["project_id"] == "proj-fsd"
        assert proj_data["org_id"] == org_id

        # List Projects
        projs_list = await send_request(app, "GET", f"/v1/organizations/{org_id}/projects")
        assert projs_list.status_code == 200
        assert len(projs_list.json()["projects"]) == 1

    asyncio.run(run())


def test_project_members_lifecycle() -> None:
    app = make_test_app()

    async def run():
        # Add member
        add_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-fsd/members",
            json_body={"user_id": "engineer@tesla.com", "role": "project_editor"},
        )
        assert add_res.status_code == 200
        assert add_res.json()["user_id"] == "engineer@tesla.com"

        # List members
        list_res = await send_request(app, "GET", "/v1/projects/proj-fsd/members")
        assert list_res.status_code == 200
        assert len(list_res.json()["members"]) == 1

        # Remove member
        del_res = await send_request(
            app,
            "DELETE",
            "/v1/projects/proj-fsd/members/engineer@tesla.com",
        )
        assert del_res.status_code == 200
        assert del_res.json()["deleted"] is True

    asyncio.run(run())


def test_scoped_api_key_generation_usage_and_revocation() -> None:
    app = make_test_app()

    async def run():
        # 1. Generate a project editor scoped key
        key_res = await send_request(
            app,
            "POST",
            "/v1/projects/proj-beta/api-keys",
            json_body={"name": "SDK Ingestion Token", "role": "service_ingestion"},
        )
        assert key_res.status_code == 200
        key_data = key_res.json()
        raw_token = key_data["api_key"]
        key_id = key_data["key_id"]
        assert raw_token.startswith("al_")

        # 2. Use the newly created raw_token to query traces or health
        health_res = await send_request(app, "GET", "/health/live", api_key=raw_token)
        assert health_res.status_code == 200

        # 3. Test permission enforcement: service_ingestion has traces:write, not system:admin
        unauthorized_admin_call = await send_request(
            app,
            "POST",
            "/v1/organizations",
            api_key=raw_token,
            json_body={"name": "Fake Org", "slug": "fake-org"},
        )
        assert unauthorized_admin_call.status_code == 403
        data = unauthorized_admin_call.json()
        assert data.get("error", {}).get("code") == "forbidden"

        # 4. Revoke the API key
        revoke_res = await send_request(
            app,
            "DELETE",
            f"/v1/projects/proj-beta/api-keys/{key_id}",
            api_key=MASTER_KEY,
        )
        assert revoke_res.status_code == 200
        assert revoke_res.json()["revoked"] is True

        # 5. Verify the revoked key is immediately rejected
        rejected_res = await send_request(
            app,
            "GET",
            "/v1/projects/proj-beta/api-keys",
            api_key=raw_token,
        )
        assert rejected_res.status_code == 401

    asyncio.run(run())
