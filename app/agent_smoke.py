"""Minimal provider-conformance agent smoke path with no lab hardware."""
from __future__ import annotations

import json
from typing import Any

from app.cloud_auth import AuthSettings, create_genai_client, resolve_auth_settings


class ExternalSmokeTestRequired(RuntimeError):
    """Raised when an external LLM call was not explicitly authorized."""


def _mock_response(settings: AuthSettings) -> dict[str, object]:
    return {
        "status": "ok",
        "provider": "mock",
        "model": settings.model,
        "external_call": False,
        "result": {
            "kind": "agent-smoke",
            "message": "Mock agent stack is available without credentials or network access.",
        },
    }


def run_agent_smoke(
    *,
    allow_external: bool = False,
    settings: AuthSettings | None = None,
    client_factory: Any | None = None,
) -> dict[str, object]:
    """Run a structured, hardware-free agent smoke test.

    Mock mode always remains local. Vertex and API-key providers require
    ``allow_external=True``; callers must map that flag to an explicit CLI
    option rather than make an API call as a side effect of normal validation.
    """
    settings = settings or resolve_auth_settings()
    if settings.error:
        raise RuntimeError(settings.error)
    if settings.is_mock:
        return _mock_response(settings)
    if not allow_external:
        raise ExternalSmokeTestRequired(
            "External LLM calls are disabled. Re-run with --smoke-test to opt in."
        )

    client = create_genai_client(settings, client_factory)
    from google.genai import types

    response = client.models.generate_content(
        model=settings.model,
        contents=(
            'Return only JSON: {"status":"ok","kind":"agent-smoke",'
            '"message":"provider reachable"}.'
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0,
        ),
    )
    try:
        payload = json.loads((response.text or "").strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError("The selected LLM returned invalid agent-smoke JSON.") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise RuntimeError("The selected LLM did not return a successful agent-smoke response.")

    return {
        "status": "ok",
        "provider": settings.provider,
        "model": settings.model,
        "external_call": True,
        "result": {
            "kind": str(payload.get("kind") or "agent-smoke"),
            "message": str(payload.get("message") or "provider reachable"),
        },
    }
