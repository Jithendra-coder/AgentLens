"""Provider Fallback & Multi-Model Routing Engine ."""

from __future__ import annotations

import logging

from agentlens.providers.adapters.anthropic_adapter import AnthropicProviderAdapter
from agentlens.providers.adapters.gemini_adapter import GeminiProviderAdapter
from agentlens.providers.adapters.openai_adapter import OpenAIProviderAdapter
from agentlens.providers.models import ModelRequest, ModelResponse, ProviderProfile
from agentlens.providers.protocol import ModelProvider, ProviderError
from agentlens.security.secrets import SecretStore

logger = logging.getLogger(__name__)


class ProviderFallbackEngine:
    """Resilient LLM generation engine with automatic provider failover and secret resolution."""

    def __init__(self, secret_store: SecretStore | None = None) -> None:
        self._secret_store = secret_store
        self._adapters: dict[str, ModelProvider] = {
            "openai": OpenAIProviderAdapter(),
            "anthropic": AnthropicProviderAdapter(),
            "gemini": GeminiProviderAdapter(),
            "custom_http": OpenAIProviderAdapter(),
        }

    def register_adapter(self, provider_type: str, adapter: ModelProvider) -> None:
        self._adapters[provider_type.lower()] = adapter

    def generate_with_fallback(
        self,
        project_id: str,
        profiles: list[ProviderProfile],
        request: ModelRequest,
    ) -> ModelResponse:
        """Execute request across ordered provider profiles, falling over on errors."""
        enabled_profiles = sorted(
            [p for p in profiles if p.enabled],
            key=lambda p: p.priority,
        )

        if not enabled_profiles:
            raise ProviderError("No enabled provider profiles available for generation.")

        errors: list[str] = []

        for profile in enabled_profiles:
            adapter = self._adapters.get(profile.provider_type.lower())
            if adapter is None:
                errors.append(
                    f"Profile '{profile.name}': Unknown provider type '{profile.provider_type}'"
                )
                continue

            api_key = ""
            if profile.secret_name and self._secret_store is not None:
                secret_val = self._secret_store.retrieve_secret(project_id, profile.secret_name)
                if secret_val is None:
                    errors.append(
                        f"Profile '{profile.name}': Secret '{profile.secret_name}' not found"
                    )
                    continue
                api_key = secret_val

            try:
                logger.info(
                    "Attempting model generation with profile '%s' (%s/%s)",
                    profile.name,
                    profile.provider_type,
                    profile.model_name,
                )
                req = ModelRequest(
                    messages=request.messages,
                    model=profile.model_name,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    json_schema=request.json_schema,
                    timeout_seconds=request.timeout_seconds,
                )
                return adapter.generate(req, api_key=api_key, base_url=profile.base_url)
            except Exception as exc:
                err_msg = f"Profile '{profile.name}' ({profile.provider_type}) failed: {exc}"
                logger.warning(err_msg)
                errors.append(err_msg)

        all_errors = "; ".join(errors)
        raise ProviderError(f"All model providers in fallback chain failed: {all_errors}")
