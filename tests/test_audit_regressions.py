"""Regression tests for issues found in the independent geographic-risk audit."""

import pandas as pd
import pytest

from app.modules.risk import engine
from app.modules.risk.concentration import (
    assess_data_quality,
    build_geographic_profile,
    fmt_pct,
    suppliers_from_trade_data,
)
from app.modules.risk.engine import ReagentRiskInput, country_exposure_overview, run_risk_assessment
from app.modules.risk.hs6_mapping import broad_category
from app.modules.risk.scenario import compute_scenario, scenario_summary_text


# F1 — WGI rows with a blank ISO3 code must not collapse into one entry
def test_import_wgi_keeps_economies_with_blank_iso(monkeypatch):
    import scripts.import_wgi as wgi

    def fake_get_json(url):
        if "/indicator/" in url:
            code = url.split("/indicator/")[1].split("?")[0]
            value = {"GOV_WGI_PV.SC": 1.0, "GOV_WGI_PV.SC_LB": 0.0, "GOV_WGI_PV.SC_UB": 2.0}[code]
            rows = [
                {"countryiso3code": "", "country": {"id": "", "value": "Taiwan, China"}, "date": "2025", "value": 83.1 * value},
                {"countryiso3code": "", "country": {"id": "", "value": "Anguilla"}, "date": "2025", "value": 90.4 * value},
                {"countryiso3code": "MEX", "country": {"id": "MX", "value": "Mexico"}, "date": "2025", "value": 55.0 * value},
                {"countryiso3code": "", "country": {"id": "", "value": "Netherlands Antilles"}, "date": "2009", "value": 70.0 * value},
            ]
            return [{"lastupdated": "2026-09-25"}, rows]
        return [{}, []]  # country metadata: no aggregates

    monkeypatch.setattr(wgi, "_get_json", fake_get_json)
    economies, _ = wgi.fetch_api()
    rows = {r["Country"]: r for r in wgi.build_rows(economies)}
    assert rows["Taiwan"]["Stability_Score"] == pytest.approx(83.1)
    assert rows["Anguilla"]["Stability_Score"] == pytest.approx(90.4)
    assert rows["Taiwan"]["ISO3"] == ""
    assert "Netherlands Antilles" not in rows  # stale (> 3 years older than newest)


def test_repository_table_has_taiwan_and_real_anguilla():
    table = engine._stability_table(engine.load_country_stability())
    assert table["Taiwan"]["score"] == pytest.approx(83.11, abs=0.01)
    assert table["Anguilla"]["score"] == pytest.approx(90.36, abs=0.01)


# F2 — country chart uses share-weighted spend, canonical names, no "Unknown" country
def test_country_exposure_overview_is_share_weighted(isolated_db, monkeypatch, usitc_folder, write_usitc_workbook):
    write_usitc_workbook(
        usitc_folder / "imports.xlsx",
        [("South Korea", "291737", [0, 97, 0]), ("China", "291737", [0, 3, 0])],
    )
    monkeypatch.setattr(engine, "load_reagent_mapping", lambda: pd.DataFrame({"Reagent_CAS": [], "HS_Code": [], "Primary_Origin": []}))
    out = run_risk_assessment(
        [
            ReagentRiskInput(name="DMT", structure="COC(=O)c1ccc(C(=O)OC)cc1", cost=100, routes={"B": {"cost": 100}}),
            ReagentRiskInput(name="Mystery", cost=50, routes={"B": {"cost": 50}}),
        ]
    )
    ce = out["summary"]["country_exposure"]
    by_country = {c["country"]: c for c in ce["countries"]}
    assert by_country["South Korea"]["by_route"]["B"] == pytest.approx(97.0)
    assert by_country["China"]["total"] == pytest.approx(3.0)
    assert "Unknown" not in by_country
    assert ce["unknown_spend"] == 50.0


# F3 — default inputs are marked; labels are neutral composite-index bands
def test_default_inputs_are_marked_and_label_is_neutral(isolated_db):
    r = run_risk_assessment([ReagentRiskInput(name="Plain reagent", cost=100, mass_g=1000)])["reagents"][0]
    comps = r["risk_index_components"]
    assert comps["components"]["operational"]["basis"] == "default"
    assert comps["components"]["regulatory"]["basis"] == "default"
    assert comps["components"]["economic"]["basis"] == "default"
    assert comps["defaults_used"] == ["operational", "regulatory", "economic"]
    assert comps["exposure_multiplier"] > 1
    assert "composite index" in r["risk_level"]
    assert "Critical" not in r["risk_level"]
    assert "Default inputs used for" in r["risk_index_note"]
    assert "purchase-quantity factor" in r["risk_index_note"]


def test_user_inputs_are_marked_as_user_input(isolated_db):
    r = run_risk_assessment(
        [ReagentRiskInput(name="X", lead_time_days=30, supplier_count=2, hazard_score=3, regulatory_score=2, substitutability=4)]
    )["reagents"][0]
    comps = r["risk_index_components"]
    assert comps["defaults_used"] == []
    assert r["lead_time"] == 30


# F4 — multi-product HS6 headings are broad; route exposure lists weak-data share
def test_multi_product_heading_is_broad_but_its_salts_is_not():
    assert "Multi-product" in broad_category("282560", "Germanium oxides and zirconium dioxides")
    assert "Multi-product" in broad_category("291560", "BUTYRIC ACID, VALERIC ACID, THEIR SALTS AND ESTERS")
    assert broad_category("291550", "PROPIONIC ACID, ITS SALTS AND ESTERS") is None
    assert broad_category("291736", "TEREPHTHALIC ACID AND ITS SALTS") is None


def test_route_exposure_marks_weak_data(isolated_db, monkeypatch, usitc_folder, write_usitc_workbook):
    write_usitc_workbook(
        usitc_folder / "imports.xlsx",
        # 3 countries so the exact match can reach HIGH data quality
        [("China", "291736", [0, 90, 0]), ("Mexico", "291736", [0, 7, 0]), ("Japan", "291736", [0, 3, 0])],
    )
    monkeypatch.setattr(engine, "load_reagent_mapping", lambda: pd.DataFrame({"Reagent_CAS": [], "HS_Code": [], "Primary_Origin": []}))
    out = run_risk_assessment(
        [
            # exact structure match -> HIGH quality
            ReagentRiskInput(name="TPA exact", structure="O=C(O)c1ccc(C(=O)O)cc1", cost=100, routes={"A": {"cost": 100}}),
            # name-only match to the same code -> MEDIUM quality
            ReagentRiskInput(name="Terephthalic acid (Polymer Grade)", cost=300, routes={"A": {"cost": 300}}),
        ]
    )
    top = out["summary"]["route_summary"][0]["largest_country_exposure"]
    assert top["country"] == "China"
    assert top["pct_of_assessed_spend"] == pytest.approx(90.0)
    assert top["weak_data_pct"] == pytest.approx(75.0)  # 270 of 360 from MEDIUM data
    assert {c["data_quality"] for c in top["contributions"]} == {"HIGH", "MEDIUM"}


# F5 / F11 — volatility and WITS exclusions cap data quality
def test_volatility_and_wits_exclusions_cap_quality():
    base = {"status": "success", "period_type": "full_year", "share_basis": "share_of_total", "hs6_mapping": {"mapping_quality": "HIGH"}}
    conc = {"tier": "HIGH", "supplier_countries_available": 6}
    volatile = {**base, "volatility": {"prior_year": 2024, "prior_top_supplier": "Canada", "top_supplier_changed": True, "total_change_pct": -70.0}}
    q = assess_data_quality(volatile, conc)
    assert q["level"] == "MEDIUM"
    assert any("top supplier in 2024 was Canada" in r for r in q["reasons"])
    assert any("-70%" in r for r in q["reasons"])
    excluded = {**base, "share_basis": "share_of_listed", "listed_count": 5, "excluded_no_quantity_count": 58}
    assert assess_data_quality(excluded, conc)["level"] == "LOW"


# F7 — one rounding rule for every displayed percentage
def test_percentages_round_half_up_consistently():
    assert fmt_pct(23.15) == "23.2%"
    assert fmt_pct(62.45) == "62.5%"
    assert fmt_pct(7.7) == "7.7%"
    assert fmt_pct(95.0) == "95%"


# F8 — summary sentence when the first route has no usable data
def test_summary_sentence_with_unknown_first_route():
    rows = [
        {"route": "A", "affected_pct": 0.0, "affected_pct_label": "0%", "exposure_tier": "UNKNOWN"},
        {"route": "B", "affected_pct": 80.0, "affected_pct_label": "80%", "exposure_tier": "HIGH"},
    ]
    text = scenario_summary_text({"type": "country_disruption", "country": "China"}, rows)
    assert text == (
        "Under a hypothetical China supply interruption, approximately 80% of the assessed "
        "reagent spend for Route B is exposed. Exposure is unknown for Route A (no usable "
        "trade data or costs)."
    )


# F12 — WITS spellings are shown canonically
def test_wits_names_are_canonicalised():
    sc = {"status": "success", "top_exporters": [{"reporter": "Korea, Rep.", "share_of_top5_pct": 60.0}]}
    s = suppliers_from_trade_data(sc)[0]
    assert s["country"] == "South Korea"
    assert s["reported_name"] == "Korea, Rep."
