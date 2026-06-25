"""Run the hardware-free provider-conformance agent smoke test."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent_smoke import ExternalSmokeTestRequired, run_agent_smoke
from app.cloud_auth import resolve_auth_settings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a small structured agent smoke test without lab hardware."
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force the offline mock provider regardless of the checkout .env.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Explicitly allow one real external LLM request for the selected provider.",
    )
    args = parser.parse_args()

    env = {"LLM_PROVIDER": "mock"} if args.mock else None
    try:
        result = run_agent_smoke(
            allow_external=args.smoke_test,
            settings=resolve_auth_settings(env),
        )
    except ExternalSmokeTestRequired as exc:
        print(json.dumps({"status": "refused", "detail": str(exc)}, indent=2))
        return 2
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
