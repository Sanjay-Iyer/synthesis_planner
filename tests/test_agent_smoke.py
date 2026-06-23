"""Offline tests for the hardware-free provider-conformance agent smoke path."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.agent_smoke import ExternalSmokeTestRequired, run_agent_smoke
from app.cloud_auth import resolve_auth_settings


def test_mock_agent_smoke_runs_without_gcloud_or_network():
    result = run_agent_smoke(settings=resolve_auth_settings({"LLM_PROVIDER": "mock"}))

    assert result["status"] == "ok"
    assert result["provider"] == "mock"
    assert result["external_call"] is False


def test_external_agent_smoke_requires_explicit_opt_in():
    settings = resolve_auth_settings({
        "LLM_PROVIDER": "vertexai",
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_LOCATION": "us-central1",
    })

    with pytest.raises(ExternalSmokeTestRequired, match="--smoke-test"):
        run_agent_smoke(settings=settings)


def test_vertex_agent_smoke_uses_vertex_client_and_returns_structure():
    client = MagicMock()
    client.models.generate_content.return_value.text = (
        '{"status":"ok","kind":"agent-smoke","message":"provider reachable"}'
    )
    factory = MagicMock(return_value=client)
    settings = resolve_auth_settings({
        "LLM_PROVIDER": "vertexai",
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "GOOGLE_CLOUD_LOCATION": "us-central1",
    })

    result = run_agent_smoke(
        allow_external=True,
        settings=settings,
        client_factory=factory,
    )

    factory.assert_called_once_with(
        vertexai=True,
        project="test-project",
        location="us-central1",
    )
    assert result["provider"] == "vertexai"
    assert result["external_call"] is True
    assert result["result"] == {
        "kind": "agent-smoke",
        "message": "provider reachable",
    }
