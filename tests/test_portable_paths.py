"""Verify that a cloned checkout does not depend on its original path or CWD."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_config_from(cwd: Path, db_dir: Path) -> dict:
    code = """
import json
from app.config import DATABASE_DIR, GEMINI_MODELS_PATH, PROJECT_ROOT, SUPPLY_CHAIN_DIR
print(json.dumps({
    'root': str(PROJECT_ROOT),
    'database': str(DATABASE_DIR),
    'models': str(GEMINI_MODELS_PATH),
    'supply_chain': str(SUPPLY_CHAIN_DIR),
}))
"""
    env = os.environ.copy()
    env["SYNTHESIS_DB_DIR"] = str(db_dir)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_runtime_paths_are_checkout_relative_from_another_working_directory(tmp_path):
    external_db = tmp_path / "work-laptop-data"
    values = _read_config_from(tmp_path, external_db)

    assert Path(values["root"]) == REPO_ROOT
    assert Path(values["database"]) == external_db
    assert Path(values["models"]) == REPO_ROOT / "data" / "gemini_models.json"
    assert Path(values["supply_chain"]) == REPO_ROOT / "data" / "supply_chain"


def test_doctor_finds_the_checkout_root_from_another_working_directory(tmp_path):
    env = os.environ.copy()
    env["LLM_PROVIDER"] = "mock"
    env.pop("GEMINI_API_KEY", None)
    env.pop("GOOGLE_API_KEY", None)
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_gcloud_setup.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    doctor = json.loads(result.stdout)

    assert Path(doctor["repo_root"]) == REPO_ROOT
    assert doctor["provider"] == "mock"


def test_runtime_source_contains_no_machine_specific_absolute_paths():
    source_files = [REPO_ROOT / "start.py"]
    source_files.extend((REPO_ROOT / "app").rglob("*.py"))
    source_files.extend((REPO_ROOT / "app").rglob("*.js"))
    source_files.extend((REPO_ROOT / "scripts").rglob("*.py"))

    forbidden_fragments = ("/home/sanjay/", "C:\\\\Users\\\\", "/Users/")
    offenders = []
    for source_file in source_files:
        text = source_file.read_text(encoding="utf-8")
        if any(fragment in text for fragment in forbidden_fragments):
            offenders.append(source_file.relative_to(REPO_ROOT).as_posix())

    assert not offenders, f"Machine-specific paths found in runtime code: {offenders}"
