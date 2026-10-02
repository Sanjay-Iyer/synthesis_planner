"""Route-level geographic summary and the reproducible demo scenario.

Fixture data (synthetic USITC workbook, full-year 2025 plus a Jan-2026 YTD
column that must be ignored):

    291736 terephthalic acid   Mexico 86 / South Korea 14
    291737 dimethyl terephth.  South Korea 97 / China 3
    290531 ethylene glycol     Canada 99 / Germany 1

Route A: TPA $600, EG $250, "Mystery additive" $150 (no HS6 -> unknown)
Route B: DMT $450, EG $75      (EG is one reagent used by both routes)
"""

import pandas as pd
import pytest

from app.modules.risk import engine
from app.modules.risk.engine import ReagentRiskInput, run_risk_assessment
from app.modules.risk.scenario import compute_scenario, items_from_assessment

TPA = "O=C(O)c1ccc(C(=O)O)cc1"
DMT = "COC(=O)c1ccc(C(=O)OC)cc1"
EG = "OCCO"


@pytest.fixture
def demo(usitc_folder, write_usitc_workbook, isolated_db, monkeypatch):
    write_usitc_workbook(
        usitc_folder / "imports.xlsx",
        [
            ("Mexico", "291736", [50, 86, 0]),
            ("South Korea", "291736", [50, 14, 5]),
            ("South Korea", "291737", [60, 97, 9]),
            ("China", "291737", [40, 3, 0]),
            ("Canada", "290531", [90, 99, 1]),
            ("Germany", "290531", [10, 1, 0]),
        ],
    )
    monkeypatch.setattr(
        engine,
        "load_country_stability",
        lambda: pd.DataFrame(
            {"Country": ["Mexico", "Canada", "South Korea", "China"], "Stability_Score": [55.0, 80.0, 82.0, 66.0]}
        ),
    )
    monkeypatch.setattr(
        engine,
        "load_reagent_mapping",
        lambda: pd.DataFrame({"Reagent_CAS": [], "HS_Code": [], "Primary_Origin": []}),
    )
    reagents = [
        ReagentRiskInput(name="Terephthalic acid", structure=TPA, cost=600, routes={"A": {"cost": 600}}),
        ReagentRiskInput(name="Ethylene glycol", structure=EG, cost=325, routes={"A": {"cost": 250}, "B": {"cost": 75}}),
        ReagentRiskInput(name="Mystery additive", cost=150, routes={"A": {"cost": 150}}),
        ReagentRiskInput(name="Dimethyl terephthalate", structure=DMT, cost=450, routes={"B": {"cost": 450}}),
    ]
    return run_risk_assessment(reagents)


def route(result, label):
    return next(r for r in result["summary"]["route_summary"] if r["route"] == label)


def test_route_membership_is_preserved(demo):
    a, b = route(demo, "A"), route(demo, "B")
    assert a["reagent_count"] == 3 and b["reagent_count"] == 2
    assert a["assessed_reagent_cost"] == 1000.0
    assert b["assessed_reagent_cost"] == 525.0
    eg = next(r for r in demo["reagents"] if r["name"] == "Ethylene glycol")
    assert eg["routes"] == {"A": {"cost": 250.0, "mass_g": 0.0}, "B": {"cost": 75.0, "mass_g": 0.0}}


def test_highest_concentration_reagent_and_high_count(demo):
    a, b = route(demo, "A"), route(demo, "B")
    assert a["high_concentration_count"] == 2
    assert set(a["high_concentration_reagents"]) == {"Terephthalic acid", "Ethylene glycol"}
    assert a["highest_concentration_reagent"]["name"] == "Ethylene glycol"  # 99% > 86%
    assert a["largest_dominant_share"]["top_supplier_share"] == pytest.approx(99.0)
    assert b["high_concentration_count"] == 2
    assert a["reagents_with_trade_data"] == 2


def test_unknown_data_exposure_is_reported_separately(demo):
    a = route(demo, "A")
    assert a["unknown_concentration_reagents"] == ["Mystery additive"]
    assert a["unknown_data_cost"] == 150.0
    assert a["unknown_data_pct"] == pytest.approx(15.0)
    assert route(demo, "B")["unknown_data_pct"] == 0


def test_largest_single_country_exposure(demo):
    a, b = route(demo, "A"), route(demo, "B")
    assert a["largest_country_exposure"]["country"] == "Mexico"
    assert a["largest_country_exposure"]["pct_of_assessed_spend"] == pytest.approx(51.6)  # 600 x 86%
    assert b["largest_country_exposure"]["country"] == "South Korea"
    assert b["largest_country_exposure"]["pct_of_assessed_spend"] == pytest.approx(83.14, abs=0.01)  # 450 x 97% / 525


def test_highest_geographic_risk_reagent_uses_country_conditions(demo):
    g = route(demo, "A")["highest_geographic_risk_reagent"]
    assert (g["name"], g["origin"], g["geographic_score"]) == ("Terephthalic acid", "Mexico", 45.0)


def test_demo_uses_full_year_and_exact_mapping(demo):
    tpa = next(r for r in demo["reagents"] if r["name"] == "Terephthalic acid")
    prov = tpa["provenance"]
    assert prov["year"] == 2025 and prov["is_partial_year"] is False
    assert prov["hs6_mapping"]["match_method"] == "inchikey"
    assert prov["hs6_mapping"]["mapping_quality"] == "HIGH"
    assert tpa["concentration"]["top_supplier_country"] == "Mexico"
    assert tpa["concentration"]["top_supplier_share"] == pytest.approx(86.0)


def test_demo_south_korea_interruption_reproduces_expected_values(demo):
    res = compute_scenario(
        items_from_assessment(demo["reagents"]), {"type": "country_disruption", "country": "South Korea"}
    )
    a = next(r for r in res["routes"] if r["route"] == "A")
    b = next(r for r in res["routes"] if r["route"] == "B")
    # A: 600 x 14% = 84 of 1000; B: 450 x 97% = 436.5 of 525
    assert a["affected_cost"] == pytest.approx(84.0)
    assert a["affected_pct"] == pytest.approx(8.4)
    assert a["exposure_tier"] == "LOW"
    assert a["exposure_tier_if_unknown_affected"] == "MEDIUM"  # 8.4% + 15% unknown
    assert b["affected_cost"] == pytest.approx(436.5)
    assert b["affected_pct"] == pytest.approx(83.14, abs=0.01)
    assert b["exposure_tier"] == "HIGH"
    assert res["summary_text"] == (
        "Under a hypothetical South Korea supply interruption, approximately 8.4% of the "
        "assessed reagent spend for Route A is exposed versus 83.1% for Route B."
    )
    assert "does not model domestic production" in res["limitations"]


def test_demo_mexico_interruption_reverses_the_picture(demo):
    res = compute_scenario(
        items_from_assessment(demo["reagents"]), {"type": "country_disruption", "country": "Mexico"}
    )
    a = next(r for r in res["routes"] if r["route"] == "A")
    b = next(r for r in res["routes"] if r["route"] == "B")
    assert a["affected_pct"] == pytest.approx(51.6)
    assert a["exposure_tier"] == "HIGH"
    assert b["affected_pct"] == 0
    assert b["exposure_tier"] == "LOW"
