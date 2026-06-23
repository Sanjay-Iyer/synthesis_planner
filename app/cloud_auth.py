"""Single source of truth for LLM provider selection and client creation.

Provider selection is deliberately explicit:

* ``mock`` is the safe offline/simulation default and has no credentials.
* ``api-key`` is a personal-laptop-only Google AI Studio path.
* ``vertexai`` uses Vertex AI with gcloud Application Default Credentials.

The Vertex branch never reads an API-key variable. This is intentional: a
copied personal ``.env`` cannot influence work-laptop authentication.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.config import load_project_env


_API_KEY_PLACEHOLDERS = {"", "your-api-key-here"}
_VERTEX_ALIASES = {"vertexai", "vertex", "gcloud"}
_API_KEY_ALIASES = {"api-key", "apikey", "api_key", "google-ai"}
_MOCK_ALIASES = {"mock", "simulation", "sim", "none", "disabled", "off"}


class ProviderConfigurationError(RuntimeError):
    """Raised when an explicitly selected provider is not usable."""


@dataclass(frozen=True)
class AuthSettings:
    """Validated, non-secret configuration for one LLM provider."""

    provider: str
    project: str | None = None
    location: str | None = None
    model: str = "gemini-2.5-flash"
    transport: str = "rest"
    api_key: str | None = None
    error: str | None = None

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock" and self.error is None

    @property
    def uses_external_llm(self) -> bool:
        return self.provider in {"vertexai", "api-key"}

    @property
    def is_ready(self) -> bool:
        if self.error:
            return False
        if self.provider == "vertexai":
            return bool(self.project and self.location and self.transport == "rest")
        if self.provider == "api-key":
            return bool(self.api_key)
        return False

    @property
    def auth_mode(self) -> str:
        if self.provider == "vertexai":
            return "vertex"
        if self.provider == "api-key":
            return "api_key"
        return "mock"

    def require_ready_external_provider(self) -> None:
        """Raise a clear error instead of changing providers implicitly."""
        if self.error:
            raise ProviderConfigurationError(self.error)
        if self.is_mock:
            raise ProviderConfigurationError(
                "LLM_PROVIDER=mock is offline-only and cannot make an external request."
            )
        if not self.is_ready:
            raise ProviderConfigurationError(
                f"LLM_PROVIDER={self.provider} is not configured for external requests."
            )


ClientFactory = Callable[..., Any]


def _api_key_from(env: Mapping[str, str]) -> str | None:
    """Read API-key variables only after ``api-key`` was selected."""
    value = (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip()
    return value if value.lower() not in _API_KEY_PLACEHOLDERS else None


def resolve_auth_settings(env: Mapping[str, str] | None = None) -> AuthSettings:
    """Resolve an explicit provider without exposing secrets.

    The absence of ``LLM_PROVIDER`` means ``mock``. It does not auto-detect an
    API key or an old Vertex flag; this avoids hidden, machine-dependent
    authentication behavior after a fresh clone.
    """
    if env is None:
        load_project_env()
        env = os.environ

    raw_provider = (env.get("LLM_PROVIDER") or "mock").strip().lower()
    model = (env.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    transport = (env.get("GOOGLE_VERTEX_API_TRANSPORT") or "rest").strip().lower()

    if raw_provider in _MOCK_ALIASES:
        return AuthSettings(provider="mock", model=model, transport=transport)

    if raw_provider in _VERTEX_ALIASES:
        # Do not call _api_key_from in this branch. Vertex must use ADC only.
        project = (env.get("GOOGLE_CLOUD_PROJECT") or "").strip() or None
        location = (env.get("GOOGLE_CLOUD_LOCATION") or "").strip() or None
        if not project:
            return AuthSettings(
                provider="vertexai",
                location=location,
                model=model,
                transport=transport,
                error=(
                    "LLM_PROVIDER=vertexai requires GOOGLE_CLOUD_PROJECT. "
                    "Then run 'gcloud auth application-default login'."
                ),
            )
        if not location:
            return AuthSettings(
                provider="vertexai",
                project=project,
                model=model,
                transport=transport,
                error="LLM_PROVIDER=vertexai requires GOOGLE_CLOUD_LOCATION.",
            )
        if transport != "rest":
            return AuthSettings(
                provider="vertexai",
                project=project,
                location=location,
                model=model,
                transport=transport,
                error=(
                    "This repository uses the REST-based google-genai client. "
                    "Set GOOGLE_VERTEX_API_TRANSPORT=rest."
                ),
            )
        return AuthSettings(
            provider="vertexai",
            project=project,
            location=location,
            model=model,
            transport=transport,
        )

    if raw_provider in _API_KEY_ALIASES:
        api_key = _api_key_from(env)
        if not api_key:
            return AuthSettings(
                provider="api-key",
                model=model,
                transport=transport,
                error=(
                    "LLM_PROVIDER=api-key requires GEMINI_API_KEY or GOOGLE_API_KEY."
                ),
            )
        return AuthSettings(
            provider="api-key",
            model=model,
            transport=transport,
            api_key=api_key,
        )

    return AuthSettings(
        provider="mock",
        model=model,
        transport=transport,
        error="LLM_PROVIDER must be 'mock', 'api-key', or 'vertexai'.",
    )


def create_genai_client(
    settings: AuthSettings,
    client_factory: ClientFactory | None = None,
) -> Any:
    """Create a Gemini client for the selected external provider only.

    The Vertex constructor receives no API key or credential object. The
    google-genai SDK resolves gcloud ADC itself on the work laptop.
    """
    settings.require_ready_external_provider()
    if client_factory is None:
        from google import genai

        client_factory = genai.Client

    if settings.provider == "vertexai":
        return client_factory(
            vertexai=True,
            project=settings.project,
            location=settings.location,
        )
    return client_factory(api_key=settings.api_key)
