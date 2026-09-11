"""Run the process-local M3 gateway with a fake development credential."""

import uvicorn

from agentlens.api import InMemoryApiKeyAuthenticator, create_app

authenticator = InMemoryApiKeyAuthenticator()
authenticator.register(
    api_key="dev-m3-key-not-real",
    key_id="dev-key",
    project_id="support-agent",
)
app = create_app(authenticator=authenticator)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
