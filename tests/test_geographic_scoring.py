"""Geographic (country-conditions) scoring, UNKNOWN handling and the composite index."""

import json

import pandas as pd
import pytest

from app.modules.risk import engine
from app.modules.risk.engine import ReagentRiskInput, composite_index, run_risk_assessment
from app.modules.risk.risk_config import COMPOSITE_WEIGHTS

STABILITY = pd.DataFrame(
    {
        "Country": ["Testland", "Korea, Rep."],
        "Stability_Score": [40.0, 80.0],
        "Score_Lower_90": [33.0, 74.0],
        "Score_Upper_90": [47.0, 86.0],
        "Year": [2025, 2025],
        "WGI_Country_Name": ["Testland", "Korea, Rep."],
    }
)


@pytest.fixture
def fixed_reference(monkeypatch, isolated_db):
    """Deterministic stability table and an empty CAS mapping."""
    monkeypatch.setattr(engine, "load_country_stability", lambda: STABILITY)
    monkeypatch.setattr(
        engine,
        "load_stability_meta",
        lambda: {"source": "Test WGI", "indicator_name": "Test stability score"},
    )
    monkeypatch.setattr(
        engine,
        "load_reagent_mapping",
        lambda: pd.DataFrame({"Reagent_CAS": [], "HS_Code": [], "Primary_Origin": []}),
    )


def assess(**kwargs):
    return run_risk_assessment([ReagentRiskInput(name="Test reagent", **kwargs)])["reagents"][0]


def test_unknown_origin_gets_no_punitive_multiplier(fixed_reference):
    r = assess(cost=10, mass_g=10)
    assert r["primary_origin"] == "Unknown"
    assert r["breakdown"]["geographic"] is None  # not 75 (= 50 x 1.5)
    assert r["geographic_exposure"]["status"] == "UNKNOWN"
    assert r["geographic_exposure"]["stability_status"] == "origin_unknown"
    assert r["risk_index_components"]["missing"] == ["geographic"]
    assert "insufficient geographic information" in r["geographic_exposure"]["explanation"]


def test_unknown_geography_renormalises_instead_of_substituting(fixed_reference):
    r = assess(cost=0, mass_g=0)  # exposure multiplier = 1
    b = r["breakdown"]
    w = COMPOSITE_WEIGHTS
    expected = (
        w["operational"] * b["operational"]
        + w["regulatory"] * b["regulatory"]
        + w["economic"] * b["economic"]
    ) / (w["operational"] + w["regulatory"] + w["economic"])
    # breakdown values are rounded to 0.1, hence the tolerance
    assert r["risk_index"] == pytest.approx(expected, abs=0.05)
    assert r["risk_index_components"]["weight_coverage"] == pytest.approx(0.70)


def test_known_stability_is_applied(fixed_reference):
    r = assess(origin="Testland", cost=0, mass_g=0)
    geo = r["geographic_exposure"]
    assert r["stability_score"] == 40.0
    assert r["breakdown"]["geographic"] == 60.0  # 100 - 40
    assert geo["stability_status"] == "known"
    assert geo["stability_ci_90"] == [33.0, 47.0]
    assert "below the midpoint" in geo["explanation"]
    assert r["risk_index_components"]["missing"] == []
    comps = r["risk_index_components"]["components"]
    expected = sum(COMPOSITE_WEIGHTS[k] * comps[k]["score"] for k in COMPOSITE_WEIGHTS)
    assert r["risk_index"] == pytest.approx(expected, abs=0.05)


def test_missing_stability_returns_explicit_status(fixed_reference):
    r = assess(origin="Atlantis")
    assert r["stability_score"] is None
    assert r["breakdown"]["geographic"] is None
    assert r["geographic_exposure"]["stability_status"] == "no_stability_data"
    assert any("No stability score for 'Atlantis'" in w for w in r["warnings"])


def test_stability_lookup_uses_canonical_country_names(fixed_reference):
    r = assess(origin="South Korea")  # table spells it "Korea, Rep."
    assert r["stability_score"] == 80.0
    assert r["geographic_exposure"]["stability_status"] == "known"


def test_concentration_is_not_duplicated_into_geographic_score(
    fixed_reference, usitc_folder, write_usitc_workbook, monkeypatch
):
    write_usitc_workbook(
        usitc_folder / "imports.xlsx",
        [("Testland", "291100", [90, 95, 0]), ("Germany", "291100", [10, 5, 0])],
    )
    monkeypatch.setattr(
        engine,
        "load_reagent_mapping",
        lambda: pd.DataFrame({"Reagent_CAS": ["X-1"], "HS_Code": ["2911.00"], "Primary_Origin": [""]}),
    )
    r = assess(cas="X-1", cost=0, mass_g=0)
    assert r["concentration"]["tier"] == "HIGH"
    assert r["breakdown"]["concentration"] == 95.0
    assert r["breakdown"]["geographic"] == 60.0  # country conditions only
    comps = r["risk_index_components"]["components"]
    assert set(comps) == set(COMPOSITE_WEIGHTS)  # no concentration component
    assert comps["geographic"]["score"] == 60.0


def test_composite_index_lists_missing_components():
    res = composite_index({"geographic": None, "operational": 50, "regulatory": 50, "economic": 50})
    assert res["score"] == pytest.approx(50.0)
    assert res["missing"] == ["geographic"]
    assert res["components"]["geographic"] == {"score": None, "weight": 0.30, "used": False}


def test_missing_stability_file_yields_no_made_up_scores(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STABILITY_FILE", tmp_path / "absent.csv")
    df = engine.load_country_stability()
    assert df.empty
    assert not (tmp_path / "absent.csv").exists()  # nothing written as a side effect


def test_repository_stability_table_is_wgi_with_provenance():
    meta = engine.load_stability_meta()
    assert meta["indicator"] == "GOV_WGI_PV.SC"
    assert "Worldwide Governance Indicators" in meta["source"]
    table = engine._stability_table(engine.load_country_stability())
    for country in ("Canada", "South Korea", "Netherlands", "Mexico", "China"):
        assert country in table, country
        assert 0 <= table[country]["score"] <= 100


# -----------------------------------------------------------------
# WGI import script (offline DataBank CSV path)
# -----------------------------------------------------------------


def test_import_wgi_reads_databank_csv(tmp_path):
    import scripts.import_wgi as wgi

    csv_path = tmp_path / "wgi.csv"
    csv_path.write_text(
        "Country Name,Country Code,Series Name,Series Code,2024 [YR2024],2025 [YR2025]\n"
        '"Korea, Rep.",KOR,PV score,GOV_WGI_PV.SC,80.1,81.7\n'
        '"Korea, Rep.",KOR,PV lower,GOV_WGI_PV.SC_LB,74,75.1\n'
        '"Korea, Rep.",KOR,PV upper,GOV_WGI_PV.SC_UB,86,88.3\n'
        "Viet Nam,VNM,PV score,GOV_WGI_PV.SC,66.0,..\n",
        encoding="utf-8",
    )
    economies, meta = wgi.read_databank_csv(csv_path)
    rows = {r["Country"]: r for r in wgi.build_rows(economies)}
    assert rows["South Korea"]["Stability_Score"] == 81.7
    assert rows["South Korea"]["Year"] == 2025
    assert rows["South Korea"]["Score_Lower_90"] == 75.1
    assert rows["Vietnam"]["Year"] == 2024  # latest non-missing value
    assert meta["input_file"].endswith("wgi.csv")
