import os
import sys
import json
import tempfile
import hashlib
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.modules.database.db import (
    init_db,
    connect_db,
    save_route_transaction,
    validate_route_without_saving,
    DB_PATH,
)
from app.modules.database.models import SaveRouteRequest

# Use a temp file in the OS temp dir rather than a hardcoded /tmp path.
TEST_DB_PATH = str(Path(tempfile.gettempdir()) / "test_dedup_synthesis_architect.db")
# Mock route fixtures live under tests/mock_data
MOCK_DATA_DIR = project_root / "tests" / "mock_data"


def get_file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def run_validation():
    print("Database deduplication validation")
    print("---------------------------------")

    # 0. Setup clean test environment
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    # Mock the DB_PATH in db module
    import app.modules.database.db

    app.modules.database.db.DB_PATH = TEST_DB_PATH

    init_db()

    # 1. Load Route A and B
    route_a_path = MOCK_DATA_DIR / "RouteA_PET.json"
    route_b_path = MOCK_DATA_DIR / "RouteB_PET.json"

    with open(route_a_path, "r", encoding="utf-8") as f:
        route_a_data = json.load(f)
    with open(route_b_path, "r", encoding="utf-8") as f:
        route_b_data = json.load(f)

    hash_a_before = get_file_hash(route_a_path)
    hash_b_before = get_file_hash(route_b_path)

    # 2. Prepare requests
    def make_req(label, filename, route_data):
        # We need to simulate the structure expected by SaveRouteRequest
        # The route_data is the full route object
        # Handle nested structure: routeA or routeB
        steps = (
            route_data.get("steps")
            or route_data.get("routeA", {}).get("steps")
            or route_data.get("routeB", {}).get("steps")
        )
        return SaveRouteRequest(
            route_label=label,
            target_molecule="PET",
            target_mass_kg=3.0,
            source_file=filename,
            route={"steps": steps},
            analysis_results={
                "total_cost": 5000.0,
                "cost_per_kg": 1600.0,
                "e_factor": 20.0,
                "overall_yield_percent": 95.0,
            },
        )

    req_a = make_req("Route A", "RouteA_PET.json", route_a_data)
    req_b = make_req("Route B", "RouteB_PET.json", route_b_data)

    # 3. Save sequences
    conn = connect_db()

    # Save A once
    save_route_transaction(conn, req_a)
    conn.commit()

    # Save A again (should deduplicate)
    save_route_transaction(conn, req_a)
    conn.commit()

    # Save B once
    save_route_transaction(conn, req_b)
    conn.commit()

    # Save B again (should deduplicate)
    save_route_transaction(conn, req_b)
    conn.commit()

    # 4. Assertions
    cursor = conn.cursor()

    # Counts
    cursor.execute("SELECT COUNT(*) FROM compounds")
    comp_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM routes")
    route_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM route_steps")
    step_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM step_reagents")
    reagent_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM analysis_runs")
    analysis_count = cursor.fetchone()[0]

    print(f"Compounds: {comp_count}")
    print(f"Routes: {route_count}")
    print(f"Route steps: {step_count}")
    print(f"Step reagents: {reagent_count}")
    print(f"Analysis runs: {analysis_count}")

    print("\nCompounds in DB:")
    cursor.execute("SELECT name, normalized_name FROM compounds")
    for row in cursor.fetchall():
        print(f" - {row[0]} ({row[1]})")

    # A. Ethylene glycol count
    cursor.execute(
        "SELECT COUNT(*) FROM compounds WHERE normalized_name LIKE '%ethyleneglycol%'"
    )
    eg_count = cursor.fetchone()[0]
    print(f"Ethylene glycol count: {eg_count} {'PASS' if eg_count == 1 else 'FAIL'}")

    # B. Terephthalic acid count
    cursor.execute(
        "SELECT COUNT(*) FROM compounds WHERE normalized_name LIKE '%terephthalicacid%'"
    )
    ta_count = cursor.fetchone()[0]
    print(f"Terephthalic acid count: {ta_count} {'PASS' if ta_count == 1 else 'FAIL'}")

    # C. Dimethyl terephthalate count
    cursor.execute(
        "SELECT COUNT(*) FROM compounds WHERE normalized_name LIKE '%dimethylterephthalate%'"
    )
    dmt_count = cursor.fetchone()[0]
    print(
        f"Dimethyl terephthalate count: {dmt_count} {'PASS' if dmt_count == 1 else 'FAIL'}"
    )

    # D. Route A definition count
    cursor.execute("SELECT COUNT(*) FROM routes WHERE source_file = 'RouteA_PET.json'")
    ra_def_count = cursor.fetchone()[0]
    print(
        f"Route A definition count: {ra_def_count} {'PASS' if ra_def_count == 1 else 'FAIL'}"
    )

    # E. Route B definition count
    cursor.execute("SELECT COUNT(*) FROM routes WHERE source_file = 'RouteB_PET.json'")
    rb_def_count = cursor.fetchone()[0]
    print(
        f"Route B definition count: {rb_def_count} {'PASS' if rb_def_count == 1 else 'FAIL'}"
    )

    # F. Analysis run count
    print(
        f"Analysis run count: {analysis_count} {'PASS' if analysis_count == 4 else 'FAIL'}"
    )

    # G. Route files unchanged
    hash_a_after = get_file_hash(route_a_path)
    hash_b_after = get_file_hash(route_b_path)
    print(
        f"RouteA_PET.json unchanged: {'PASS' if hash_a_before == hash_a_after else 'FAIL'}"
    )
    print(
        f"RouteB_PET.json unchanged: {'PASS' if hash_b_before == hash_b_after else 'FAIL'}"
    )

    # I. validate-route does not write
    count_before = conn.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
    validate_route_without_saving(req_a)
    count_after = conn.execute("SELECT COUNT(*) FROM compounds").fetchone()[0]
    print(
        f"validate-route does not write: {'PASS' if count_before == count_after else 'FAIL'}"
    )

    # Final check
    all_pass = (
        eg_count == 1
        and ta_count == 1
        and dmt_count == 1
        and ra_def_count == 1
        and rb_def_count == 1
        and analysis_count == 4
        and hash_a_before == hash_a_after
        and hash_b_before == hash_b_after
        and count_before == count_after
    )

    print(f"\nFinal result: {'PASS' if all_pass else 'FAIL'}")

    conn.close()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    run_validation()
