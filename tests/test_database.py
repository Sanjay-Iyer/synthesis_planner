import pytest
import sqlite3
import os
import json
from app.modules.database.db import (
    init_db,
    connect_db,
    upsert_compound,
    save_route_transaction,
    validate_route_without_saving,
    DB_PATH,
)
from app.modules.database.models import SaveRouteRequest

# Mock DB Path for testing
TEST_DB_PATH = "tests/test_synthesis_architect.db"


@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Create a clean test database before each test."""
    if not os.path.exists("tests"):
        os.makedirs("tests")
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    # Monkeypatch the DB_PATH in db module
    import app.modules.database.db

    monkeypatch.setattr(app.modules.database.db, "DB_PATH", TEST_DB_PATH)

    init_db()
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def test_db_initialization():
    """Verify all tables are created."""
    conn = sqlite3.connect(TEST_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    assert "compounds" in tables
    assert "routes" in tables
    assert "route_steps" in tables
    assert "step_reagents" in tables
    assert "analysis_runs" in tables
    conn.close()


def test_save_route_and_deduplication():
    """Test saving a route and reusing compounds."""
    # 1. Save Route A
    route_data = {
        "route_label": "Route A",
        "target_molecule": "PET",
        "source_file": "test.json",
        "route": {
            "steps": [
                {
                    "step_id": 1,
                    "name": "Esterification",
                    "reagents": [
                        {
                            "name": "Ethylene glycol",
                            "smiles": "OCCO",
                            "mw": 62.07,
                            "equivalents": 1.0,
                            "mass": 62.07,
                        },
                        {
                            "name": "Terephthalic acid",
                            "smiles": "O=C(O)c1ccc(C(=O)O)cc1",
                            "mw": 166.13,
                            "equivalents": 1.0,
                            "mass": 166.13,
                        },
                    ],
                }
            ]
        },
        "analysis_results": {
            "total_cost": 100.0,
            "cost_per_kg": 33.3,
            "e_factor": 1.5,
            "overall_yield_percent": 90.0,
        },
    }

    request = SaveRouteRequest(**route_data)
    conn = connect_db()
    result = save_route_transaction(conn, request)
    conn.commit()

    # Check counts
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM compounds")
    assert cursor.fetchone()[0] == 2

    # 2. Save Route B (reusing Ethylene glycol)
    route_data_b = {
        "route_label": "Route B",
        "target_molecule": "PET",
        "source_file": "test_b.json",
        "route": {
            "steps": [
                {
                    "step_id": 1,
                    "name": "Transesterification",
                    "reagents": [
                        {
                            "name": "Ethylene glycol",
                            "smiles": "OCCO",
                            "mw": 62.07,
                            "equivalents": 1.0,
                            "mass": 62.07,
                        },
                        {
                            "name": "Dimethyl terephthalate",
                            "smiles": "COC(=O)c1ccc(C(=O)OC)cc1",
                            "mw": 194.18,
                            "equivalents": 1.0,
                            "mass": 194.18,
                        },
                    ],
                }
            ]
        },
        "analysis_results": {"total_cost": 150.0, "cost_per_kg": 50.0, "e_factor": 2.0},
    }

    request_b = SaveRouteRequest(**route_data_b)
    result_b = save_route_transaction(conn, request_b)
    conn.commit()

    # Check counts - should be 3 now (EG reused, DMT new)
    cursor.execute("SELECT COUNT(*) FROM compounds")
    assert cursor.fetchone()[0] == 3

    # Verify Ethylene glycol last_seen updated
    cursor.execute(
        "SELECT first_seen, last_seen FROM compounds WHERE name = 'Ethylene glycol'"
    )
    row = cursor.fetchone()
    # In a fast test they might be identical, but we can check the count of usages
    cursor.execute(
        "SELECT COUNT(*) FROM step_reagents JOIN compounds ON step_reagents.compound_uuid = compounds.uuid WHERE compounds.name = 'Ethylene glycol'"
    )
    assert cursor.fetchone()[0] == 2

    conn.close()


def test_duplicate_route_hash():
    """Test that saving exact same route creates new analysis run but reuses route uuid."""
    route_data = {
        "route_label": "Route A",
        "target_molecule": "PET",
        "route": {
            "steps": [
                {
                    "step_id": 1,
                    "name": "Step 1",
                    "reagents": [
                        {"name": "R1", "mw": 10.0, "equivalents": 1.0, "mass": 10.0}
                    ],
                }
            ]
        },
        "analysis_results": {"total_cost": 10, "cost_per_kg": 1, "e_factor": 0.5},
    }

    request = SaveRouteRequest(**route_data)
    conn = connect_db()

    # Save 1
    res1 = save_route_transaction(conn, request)
    conn.commit()

    # Save 2 (identical route)
    res2 = save_route_transaction(conn, request)
    conn.commit()

    assert res1["route_uuid"] == res2["route_uuid"]
    assert res1["analysis_run_uuid"] != res2["analysis_run_uuid"]

    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM routes")
    assert cursor.fetchone()[0] == 1

    cursor.execute("SELECT COUNT(*) FROM analysis_runs")
    assert cursor.fetchone()[0] == 2

    conn.close()


def test_validate_route_dry_run():
    """Test that validate-route does not write to DB."""
    route_data = {
        "route_label": "Route A",
        "target_molecule": "PET",
        "route": {
            "steps": [
                {
                    "step_id": 1,
                    "name": "Step 1",
                    "reagents": [
                        {
                            "name": "New Molecule",
                            "mw": 10.0,
                            "equivalents": 1.0,
                            "mass": 10.0,
                        }
                    ],
                }
            ]
        },
        "analysis_results": {"total_cost": 10, "cost_per_kg": 1, "e_factor": 0.5},
    }

    request = SaveRouteRequest(**route_data)
    val = validate_route_without_saving(request)

    assert val["new_compounds"] == 1

    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM compounds")
    assert cursor.fetchone()[0] == 0
    conn.close()


def test_ambiguous_compound():
    """Test detection of ambiguous compounds."""
    route_data = {
        "route_label": "Route A",
        "target_molecule": "PET",
        "route": {
            "steps": [
                {
                    "step_id": 1,
                    "name": "Step 1",
                    "reagents": [
                        {
                            "name": "PET Intermediate (Oligomer)",
                            "mw": 100.0,
                            "equivalents": 1.0,
                            "mass": 100.0,
                        }
                    ],
                }
            ]
        },
        "analysis_results": {"total_cost": 10, "cost_per_kg": 1, "e_factor": 0.5},
    }

    request = SaveRouteRequest(**route_data)
    conn = connect_db()
    save_route_transaction(conn, request)
    conn.commit()

    cursor = conn.cursor()
    cursor.execute(
        "SELECT is_defined_structure FROM compounds WHERE name LIKE '%Oligomer%'"
    )
    assert cursor.fetchone()[0] == 0
    conn.close()
