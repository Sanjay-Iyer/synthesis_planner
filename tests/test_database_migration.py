import os
import sqlite3
import pytest
from app.modules.database.db import init_db, connect_db
import app.modules.database.db as db_mod


@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test.db"
    # Monkeypatch the DB_PATH in the module
    old_path = db_mod.DB_PATH
    db_mod.DB_PATH = db_path
    yield db_path
    db_mod.DB_PATH = old_path


def test_init_db_adds_hs6_code_to_new_database(temp_db):
    """Confirm a fresh database has the hs6_code column."""
    init_db()
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(compounds)")
    cols = [c[1] for c in cursor.fetchall()]
    assert "hs6_code" in cols
    conn.close()


def test_init_db_migrates_existing_database_without_hs6_code(temp_db):
    """Confirm an old schema database is migrated to include hs6_code."""
    # 1. Create a "legacy" database without hs6_code, but with other required columns
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE compounds (
            uuid TEXT PRIMARY KEY, 
            name TEXT, 
            normalized_name TEXT, 
            smiles TEXT, 
            canonical_smiles TEXT, 
            selfies TEXT, 
            inchikey TEXT,
            formula TEXT,
            mw REAL,
            exact_mw REAL,
            cas TEXT,
            compound_type TEXT,
            is_defined_structure INTEGER,
            dedupe_basis TEXT,
            dedupe_confidence TEXT,
            first_seen TEXT,
            last_seen TEXT,
            notes TEXT
        )
    """)
    conn.commit()
    conn.close()

    # 2. Run init_db which should migrate it
    init_db()

    # 3. Check for the column
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(compounds)")
    cols = [c[1] for c in cursor.fetchall()]
    assert "hs6_code" in cols
    conn.close()


def test_init_db_migration_is_idempotent(temp_db):
    """Confirm running init_db multiple times does not crash."""
    init_db()
    init_db()  # Should not raise OperationalError

    conn = sqlite3.connect(str(temp_db))
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(compounds)")
    cols = [c[1] for c in cursor.fetchall()]
    assert "hs6_code" in cols
    conn.close()
