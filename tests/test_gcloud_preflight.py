"""CI-safe conformance tests for portable gcloud/Vertex deployment."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from app.cloud_auth import create_genai_client, resolve_auth_settings
from app.gcloud_preflight import validate_vertexai_setup
from app.modules.extraction.service import MockRouteExtractor, get_extractor

VERTEX_ENV = {
    "LLM_PROVIDER": "vertexai",
    "GOOGLE_CLOUD_PROJECT": "test-vertex-project",
    "GOOGLE_CLOUD_LOCATION": "us-central1",
    "GEMINI_MODEL": "gemini-2.5-flash",
    "GOOGLE_VERTEX_API_TRANSPORT": "rest",
    "GEMINI_API_KEY": "must-not-be-used",
}


class _ApiKeyPoison(dict):
    """Fails the test if Vertex configuration even consults an API-key key."""

    def get(self, key, default=None):
        if key in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
            raise AssertionError("Vertex mode must not read API-key variables")
        return super().get(key, default)


def _gcloud_runner(command, **_kwargs):
    if command[2:3] == ["list"]:
        return subprocess.CompletedProcess(command, 0, "engineer@example.com\n", "")
    if command[2:4] == ["application-default", "print-access-token"]:
        return subprocess.CompletedProcess(command, 0, "temporary-token\n", "")
    return subprocess.CompletedProcess(command, 1, "", "unexpected command")


def test_vertex_mode_never_reads_or_passes_api_keys():
    env = _ApiKeyPoison(
        {key: value for key, value in VERTEX_ENV.items() if "API_KEY" not in key}
    )
    settings = resolve_auth_settings(env)
    client_factory = MagicMock(return_value=MagicMock())

    create_genai_client(settings, client_factory)

    assert settings.is_ready is True
    assert settings.api_key is None
    client_factory.assert_called_once_with(
        vertexai=True,
        project="test-vertex-project",
        location="us-central1",
    )


def test_vertex_mode_requires_project_and_location():
    missing_project = resolve_auth_settings({"LLM_PROVIDER": "vertexai"})
    missing_location = resolve_auth_settings(
        {
            "LLM_PROVIDER": "vertexai",
            "GOOGLE_CLOUD_PROJECT": "test-project",
        }
    )

    assert "GOOGLE_CLOUD_PROJECT" in (missing_project.error or "")
    assert "GOOGLE_CLOUD_LOCATION" in (missing_location.error or "")


def test_vertex_mode_requires_rest_transport():
    settings = resolve_auth_settings(
        {
            "LLM_PROVIDER": "vertexai",
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
            "GOOGLE_VERTEX_API_TRANSPORT": "grpc",
        }
    )

    assert settings.is_ready is False
    assert "GOOGLE_VERTEX_API_TRANSPORT=rest" in (settings.error or "")


def test_explicit_invalid_vertex_configuration_does_not_silently_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "vertexai")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)

    try:
        get_extractor()
    except RuntimeError as exc:
        assert "GOOGLE_CLOUD_PROJECT" in str(exc)
    else:  # pragma: no cover - safety regression path
        raise AssertionError("Explicit Vertex mode must not silently fall back")


def test_doctor_reports_adc_account_and_checkout_details_without_token():
    client_factory = MagicMock(return_value=MagicMock())
    alternate_root = Path("different") / "clone" / "location"
    report = validate_vertexai_setup(
        env=VERTEX_ENV,
        command_runner=_gcloud_runner,
        executable_finder=lambda _: "C:/GoogleCloudSDK/bin/gcloud.cmd",
        client_factory=client_factory,
        repo_root=alternate_root,
        python_executable="/conda/envs/llm/python",
    )
    data = report.to_dict()

    assert report.passed is True
    assert Path(data["repo_root"]) == alternate_root.resolve()
    assert data["python_executable"] == "/conda/envs/llm/python"
    assert data["gcloud_account"] == "engineer@example.com"
    assert data["adc_status"] == "available"
    assert data["vertex_api_access"] == "appears-configured"
    assert "temporary-token" not in str(data)


def test_mock_mode_is_healthy_without_gcloud_or_credentials():
    report = validate_vertexai_setup(
        env={"LLM_PROVIDER": "mock"},
        executable_finder=lambda _: None,
    )

    assert report.passed is True
    assert report.provider == "mock"
    assert report.adc_status == "not-required"
    assert report.next_command.endswith("--mock")


def test_mock_provider_uses_heuristic_extractor_without_credentials(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    assert isinstance(get_extractor(), MockRouteExtractor)


def test_vertex_doctor_fails_clearly_when_adc_is_unavailable():
    def missing_adc_runner(command, **_kwargs):
        if command[2:3] == ["list"]:
            return subprocess.CompletedProcess(command, 0, "engineer@example.com\n", "")
        return subprocess.CompletedProcess(command, 1, "", "not logged in")

    report = validate_vertexai_setup(
        env=VERTEX_ENV,
        command_runner=missing_adc_runner,
        executable_finder=lambda _: "gcloud",
        client_factory=MagicMock(),
    )

    assert report.passed is False
    assert report.adc_status == "unavailable"
    assert report.next_command == "gcloud auth application-default login"


def test_real_smoke_is_skipped_unless_explicitly_requested():
    client = MagicMock()
    report = validate_vertexai_setup(
        env=VERTEX_ENV,
        command_runner=_gcloud_runner,
        executable_finder=lambda _: "gcloud",
        client_factory=lambda **_kwargs: client,
        smoke_test=False,
    )

    assert report.passed is True
    client.models.generate_content.assert_not_called()
    checks = {check.name: check for check in report.checks}
    assert checks["vertex-api-smoke-test"].passed is True
