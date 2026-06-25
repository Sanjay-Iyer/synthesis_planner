"""Validate the repo's gcloud/Vertex AI setup without exposing credentials."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow this script to run from any working directory after the repository is
# cloned to a different location.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.gcloud_preflight import validate_vertexai_setup


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate gcloud ADC and the repo's Vertex AI configuration."
    )
    parser.add_argument(
        "--check-adc",
        action="store_true",
        help="Ask gcloud to validate Application Default Credentials.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Make one minimal authenticated Vertex AI request after validation.",
    )
    args = parser.parse_args()
    report = validate_vertexai_setup(
        check_adc=args.check_adc or args.smoke_test,
        smoke_test=args.smoke_test,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
