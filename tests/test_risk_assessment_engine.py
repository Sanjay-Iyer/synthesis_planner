import pytest
from app.modules.risk.engine import ReagentRiskInput, run_risk_assessment
import app.modules.database.db as db_mod
import sqlite3

@pytest.fixture
def mock_db(tmp_path):
    db_path = tmp_path / "test_risk.db"
    old_path = db_mod.DB_PATH
    db_mod.DB_PATH = db_path
    db_mod.init_db()
    yield db_path
    db_mod.DB_PATH = old_path

def test_risk_assessment_does_not_crash_without_hs6_code(mock_db):
    """Confirm the engine works even if no HS6 mapping is found."""
    reagents = [ReagentRiskInput(name="Test Chemical", mass_g=1.0, cost=1.0)]
    results = run_risk_assessment(reagents)
    assert len(results["reagents"]) == 1
    assert any("No HS6 code available" in w for w in results["reagents"][0]["warnings"])

def test_risk_assessment_does_not_crash_with_unknown_origin(mock_db):
    """Confirm 'Unknown' origin is handled gracefully."""
    reagents = [ReagentRiskInput(name="Test Chemical", origin="Unknown", mass_g=1.0, cost=1.0)]
    results = run_risk_assessment(reagents)
    assert results["reagents"][0]["primary_origin"] == "Unknown"
    assert results["reagents"][0]["stability_score"] == 50.0

def test_stability_row_defined_before_use(mock_db):
    """This essentially tests that run_risk_assessment executes without NameError."""
    reagents = [ReagentRiskInput(name="Test Chemical", mass_g=1.0, cost=1.0)]
    # This would raise NameError if stability_row was not defined
    results = run_risk_assessment(reagents)
    assert "reagents" in results

def test_risk_assessment_returns_warnings_for_missing_hs6_code(mock_db):
    """Verify that warnings are correctly populated."""
    reagents = [ReagentRiskInput(name="Mystery Molecule", mass_g=1.0, cost=1.0)]
    results = run_risk_assessment(reagents)
    warnings = results["reagents"][0]["warnings"]
    assert any("No HS6 code available" in w for w in warnings)
