"""Secret-free doctor and opt-in Vertex AI readiness checks."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from shutil import which
from typing import Callable, Mapping

from app.cloud_auth import AuthSettings, create_genai_client, resolve_auth_settings
from app.config import ENV_FILE_PATH, PROJECT_ROOT


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    repo_root: str
    python_executable: str
    conda_environment: str | None
    dotenv_path: str | None
    provider: str
    project: str | None
    location: str | None
    model: str
    transport: str
    gcloud_installed: bool
    gcloud_account: str | None
    adc_status: str
    vertex_api_access: str
    next_command: str
    checks: list[PreflightCheck]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        """Return diagnostics without credential values, tokens, or raw stderr."""
        return {
            "passed": self.passed,
            "repo_root": self.repo_root,
            "python_executable": self.python_executable,
            "conda_environment": self.conda_environment,
            "dotenv_path": self.dotenv_path,
            "provider": self.provider,
            "project": self.project,
            "location": self.location,
            "model": self.model,
            "transport": self.transport,
            "gcloud_installed": self.gcloud_installed,
            "gcloud_account": self.gcloud_account,
            "adc_status": self.adc_status,
            "vertex_api_access": self.vertex_api_access,
            "next_command": self.next_command,
            "checks": [asdict(check) for check in self.checks],
        }


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
ClientFactory = Callable[..., object]


def _run_text_command(
    command: list[str], command_runner: CommandRunner
) -> tuple[bool, str]:
    """Run a bounded local gcloud command and return only non-secret text."""
    try:
        result = command_runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    return result.returncode == 0, (result.stdout or "").strip()


def _next_command(
    settings: AuthSettings,
    *,
    gcloud_installed: bool,
    adc_status: str,
    smoke_test: bool,
) -> str:
    if settings.error:
        return "Copy .env.vertexai.example to .env and set LLM_PROVIDER, project, location, and transport."
    if settings.is_mock:
        return "python scripts\\run_agent_smoke.py --mock"
    if settings.provider == "api-key":
        return "python scripts\\run_agent_smoke.py --smoke-test"
    if not gcloud_installed:
        return (
            "Install Google Cloud CLI, then run: gcloud auth application-default login"
        )
    if adc_status != "available":
        return "gcloud auth application-default login"
    if not smoke_test:
        return "python scripts\\validate_gcloud_setup.py --check-adc --smoke-test"
    return "python scripts\\run_agent_smoke.py --smoke-test"


def validate_vertexai_setup(
    *,
    env: Mapping[str, str] | None = None,
    check_adc: bool = True,
    smoke_test: bool = False,
    command_runner: CommandRunner = subprocess.run,
    executable_finder: Callable[[str], str | None] = which,
    client_factory: ClientFactory | None = None,
    repo_root: Path = PROJECT_ROOT,
    python_executable: str | None = None,
) -> PreflightReport:
    """Report deployment readiness without printing a key or access token.

    ``check_adc`` may refresh a local gcloud credential. ``smoke_test`` is the
    only branch that makes a Vertex AI request, and must be explicitly passed
    by a human command; it is never used by the test suite.
    """
    settings = resolve_auth_settings(env)
    checks: list[PreflightCheck] = []
    python_executable = python_executable or sys.executable
    gcloud_required = settings.provider == "vertexai"

    config_ok = settings.error is None
    checks.append(
        PreflightCheck(
            name="provider-configuration",
            passed=config_ok,
            detail=(
                f"LLM_PROVIDER resolves to {settings.provider}."
                if config_ok
                else settings.error or "Provider configuration is invalid."
            ),
        )
    )

    gcloud_path = executable_finder("gcloud")
    gcloud_installed = bool(gcloud_path)
    checks.append(
        PreflightCheck(
            name="gcloud-cli",
            passed=not gcloud_required or gcloud_installed,
            detail=(
                "gcloud CLI was found on PATH."
                if gcloud_installed
                else (
                    "gcloud is not installed; it is not required for the selected provider."
                    if not gcloud_required
                    else "gcloud CLI was not found on PATH. Install Google Cloud CLI first."
                )
            ),
        )
    )

    gcloud_account: str | None = None
    if gcloud_installed:
        account_ok, account_text = _run_text_command(
            [
                gcloud_path,
                "auth",
                "list",
                "--filter=status:ACTIVE",
                "--format=value(account)",
            ],
            command_runner,
        )
        gcloud_account = (account_text or None) if account_ok else None
        checks.append(
            PreflightCheck(
                name="gcloud-active-account",
                passed=not gcloud_required or bool(gcloud_account),
                detail=(
                    "An active gcloud account is configured."
                    if gcloud_account
                    else "No active gcloud account was found. Run 'gcloud auth login'."
                ),
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="gcloud-active-account",
                passed=not gcloud_required,
                detail="Skipped because gcloud CLI is unavailable.",
            )
        )

    adc_status = "not-required"
    if gcloud_required:
        if not gcloud_installed:
            adc_status = "unavailable"
        elif not check_adc:
            adc_status = "not-checked"
        else:
            adc_ok, _token = _run_text_command(
                [gcloud_path, "auth", "application-default", "print-access-token"],
                command_runner,
            )
            adc_status = "available" if adc_ok and _token else "unavailable"
    checks.append(
        PreflightCheck(
            name="application-default-credentials",
            passed=not gcloud_required or adc_status in {"available", "not-checked"},
            detail={
                "available": "Application Default Credentials are available.",
                "not-checked": "Not checked; rerun with --check-adc to validate gcloud ADC.",
                "unavailable": "ADC is unavailable. Run 'gcloud auth application-default login'.",
                "not-required": "Not required for the selected provider.",
            }[adc_status],
        )
    )

    client: object | None = None
    if settings.uses_external_llm and settings.is_ready:
        try:
            client = create_genai_client(settings, client_factory)
            checks.append(
                PreflightCheck(
                    name="selected-provider-sdk-client",
                    passed=True,
                    detail="google-genai accepted the selected provider configuration.",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive SDK boundary
            checks.append(
                PreflightCheck(
                    name="selected-provider-sdk-client",
                    passed=False,
                    detail=f"Could not construct the selected provider client: {exc}",
                )
            )
    elif settings.is_mock:
        checks.append(
            PreflightCheck(
                name="selected-provider-sdk-client",
                passed=True,
                detail="Mock/simulation provider requires no SDK client or credentials.",
            )
        )
    else:
        checks.append(
            PreflightCheck(
                name="selected-provider-sdk-client",
                passed=False,
                detail="Skipped because provider configuration is incomplete.",
            )
        )

    vertex_api_access = "not-applicable"
    if settings.provider == "vertexai":
        vertex_api_access = (
            "appears-configured"
            if client and adc_status == "available"
            else "not-verified"
        )

    if smoke_test:
        if not (
            settings.provider == "vertexai" and client and adc_status == "available"
        ):
            checks.append(
                PreflightCheck(
                    name="vertex-api-smoke-test",
                    passed=False,
                    detail="Skipped because Vertex configuration, gcloud ADC, or SDK validation failed.",
                )
            )
        else:
            try:
                client.models.generate_content(  # type: ignore[union-attr]
                    model=settings.model,
                    contents='Reply exactly with "gcloud-auth-ok".',
                )
                vertex_api_access = "verified"
                checks.append(
                    PreflightCheck(
                        name="vertex-api-smoke-test",
                        passed=True,
                        detail="A minimal authenticated Vertex AI request succeeded.",
                    )
                )
            except Exception as exc:  # pragma: no cover - real external boundary
                vertex_api_access = "not-verified"
                checks.append(
                    PreflightCheck(
                        name="vertex-api-smoke-test",
                        passed=False,
                        detail=f"Vertex AI request failed: {exc}",
                    )
                )
    else:
        checks.append(
            PreflightCheck(
                name="vertex-api-smoke-test",
                passed=True,
                detail="Not run; use --smoke-test to make the one real Vertex AI request.",
            )
        )

    return PreflightReport(
        repo_root=str(repo_root.resolve()),
        python_executable=python_executable,
        conda_environment=os.environ.get("CONDA_DEFAULT_ENV") or None,
        dotenv_path=str(ENV_FILE_PATH) if ENV_FILE_PATH.is_file() else None,
        provider=settings.provider,
        project=settings.project,
        location=settings.location,
        model=settings.model,
        transport=settings.transport,
        gcloud_installed=gcloud_installed,
        gcloud_account=gcloud_account,
        adc_status=adc_status,
        vertex_api_access=vertex_api_access,
        next_command=_next_command(
            settings,
            gcloud_installed=gcloud_installed,
            adc_status=adc_status,
            smoke_test=smoke_test,
        ),
        checks=checks,
    )
