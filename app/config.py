"""
Central path configuration — single source of truth for filesystem locations.

All paths are derived from the project root using ``pathlib`` so they adapt
their slash direction to the host OS (Windows ``\\`` vs POSIX ``/``)
automatically. No Linux- or Windows-specific path strings are hardcoded here.

The database directory can be overridden per-machine with the
``SYNTHESIS_DB_DIR`` environment variable (useful when the data lives outside
the repo, e.g. on a shared drive).
"""
import os
from pathlib import Path

# app/config.py -> app/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE_PATH = PROJECT_ROOT / ".env"


def load_project_env() -> Path | None:
    """Load this checkout's optional ``.env`` without relying on the CWD.

    Existing process variables win, allowing CI and tests to override local
    settings safely. The returned path is useful for doctor diagnostics and is
    never read from another checkout or the caller's working directory.
    """
    if not ENV_FILE_PATH.is_file():
        return None

    from dotenv import load_dotenv

    load_dotenv(ENV_FILE_PATH, override=False)
    return ENV_FILE_PATH


# Configuration used by non-LLM modules (for example SYNTHESIS_DB_DIR) should
# see the same checkout-local .env as the LLM provider configuration.
load_project_env()

# Database directory: env override, otherwise <project_root>/database
DATABASE_DIR = Path(os.environ.get("SYNTHESIS_DB_DIR", PROJECT_ROOT / "database"))

# Concrete data files / stores
SYNTHESIS_DB_PATH = DATABASE_DIR / "synthesis_architect.db"
WITS_EXPORTS_DB_PATH = DATABASE_DIR / "wits_exports.json"
COMPOUND_HS6_MAP_PATH = DATABASE_DIR / "compound_hs6_map.json"
DATA_TO_ADD_DIR = DATABASE_DIR / "data_to_add"
GEMINI_MODELS_PATH = PROJECT_ROOT / "data" / "gemini_models.json"

# Supply-chain data drop folder. Any USITC DataWeb (or compatible) export
# dropped here is live-scanned and indexed by the supply_chain module so the
# Risk Audit page can use it for origin lookups and concentration risk.
SUPPLY_CHAIN_DIR = PROJECT_ROOT / "data" / "supply_chain"
