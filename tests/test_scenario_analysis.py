"""Deterministic scenario / shock analysis over assessed reagents."""

import pytest

from app.modules.risk.scenario import ALL_REAGENTS_ROUTE, compute_scenario


def item(name, cost, suppliers, routes=None, coverage="all_reported_countries", lead=14):
    """A scenario input as produced by items_from_assessment()."""
    has_data = suppliers is not None
    suppliers = suppliers or []
    return {
        "name": name,
        "cost": cost,
        "routes": routes if routes is not None else {"A": {"cost": cost}},
        "lead_time_days": lead,
        "suppliers": [{"country": c, "share_pct": s} for c, s in suppliers],
        "share_basis": "share_of_total" if coverage == "all_reported_countries" else "share_of_listed",
        "coverage": coverage,
        "has_trade_data": has_data,
        "top_supplier_country": suppliers[0][0] if suppliers else None,
        "source_label": "test data",
    }


def route(result, label):
    return next(r for r in result["routes"] if r["route"] == label)


def reagent(result, name):
    return next(r for r in result["reagents"] if r["name"] == name)


# Route A: one expensive reagent 95% from China. Route B: diversified.
ROUTE_A = [
    item("Reagent X", 430.0, [("China", 95.0), ("South Korea", 3.0), ("Germany", 2.0)]),
    item("Reagent Y", 570.0, [("Germany", 60.0), ("USA", 40.0)]),
]
ROUTE_B = [
    item("Reagent Z", 800.0, [("India", 30.0), ("China", 10.0), ("Japan", 60.0)], routes={"B": {"cost": 800.0}}),
    item("Reagent W", 200.0, [("Brazil", 100.0)], routes={"B": {"cost": 200.0}}),
]


def test_dominant_country_disruption_calculates_affected_exposure():
    res = compute_scenario(ROUTE_A + ROUTE_B, {"type": "country_disruption", "country": "China"})

    x = reagent(res, "Reagent X")
    assert x["status"] == "EXPOSED"
    assert x["exposure_share_pct"] == 95.0
    assert x["routes"]["A"]["affected_cost"] == pytest.approx(408.5)  # 430 x 95%
    assert "95% sourcing exposure affected" in x["assessment"]
    assert "high dependency on disrupted country" in x["assessment"]
    assert "limited observed alternative sourcing" in x["assessment"]  # 5% remains
    assert "unavailable" not in x["assessment"].lower()

    a = route(res, "A")
    assert a["assessed_reagent_cost"] == 1000.0
    assert a["affected_cost"] == pytest.approx(408.5)
    assert a["affected_pct"] == pytest.approx(40.85)
    assert a["exposure_tier"] == "HIGH"
    assert a["exposure_label"] == "highly exposed"
    assert a["high_dependency_reagents"] == ["Reagent X"]

    b = route(res, "B")
    assert b["affected_pct"] == pytest.approx(8.0)  # 800 x 10% of 1000
    assert b["exposure_tier"] == "LOW"
    assert b["exposure_label"] == "lower exposure"


def test_unrelated_country_disruption_has_zero_impact():
    res = compute_scenario(ROUTE_A, {"type": "country_disruption", "country": "Chile"})
    a = route(res, "A")
    assert a["affected_cost"] == 0
    assert a["affected_pct"] == 0
    assert a["exposure_tier"] == "LOW"
    assert all(r["status"] == "NOT_EXPOSED" for r in res["reagents"])


def test_two_reagents_from_affected_country_aggregate():
    items = [
        item("R1", 100.0, [("China", 80.0), ("India", 20.0)]),
        item("R2", 300.0, [("China", 50.0), ("Japan", 50.0)]),
        item("R3", 600.0, [("Germany", 100.0)]),
    ]
    res = compute_scenario(items, {"type": "country_disruption", "country": "China"})
    a = route(res, "A")
    # 100 x 80% + 300 x 50% = 230 of 1000
    assert a["affected_cost"] == pytest.approx(230.0)
    assert a["affected_pct"] == pytest.approx(23.0)
    assert a["exposure_tier"] == "MEDIUM"
    assert {e["name"] for e in a["exposed_reagents"]} == {"R1", "R2"}


def test_missing_country_data_is_unknown_not_zero_risk():
    items = [item("No-data reagent", 500.0, None)]
    res = compute_scenario(items, {"type": "country_disruption", "country": "China"})
    r = reagent(res, "No-data reagent")
    assert r["status"] == "UNKNOWN"
    assert r["exposure_share_pct"] is None
    a = route(res, "A")
    assert a["exposure_tier"] == "UNKNOWN"
    assert a["unknown_pct"] == 100.0
    assert a["unknown_reagents"] == ["No-data reagent"]


def test_partly_unknown_route_reports_upper_bound():
    items = [
        item("Known", 700.0, [("Germany", 100.0)]),
        item("Unknown", 300.0, None),
    ]
    res = compute_scenario(items, {"type": "country_disruption", "country": "China"})
    a = route(res, "A")
    assert a["exposure_tier"] == "LOW"
    assert a["exposure_tier_if_unknown_affected"] == "HIGH"  # 0% + 30% unknown
    assert "no trade data" in a["note"]


def test_listed_only_data_without_the_country_is_not_listed():
    items = [item("WITS reagent", 100.0, [("Belgium", 54.0), ("Germany", 24.0)], coverage="listed_only")]
    res = compute_scenario(items, {"type": "country_disruption", "country": "China"})
    r = reagent(res, "WITS reagent")
    assert r["status"] == "NOT_LISTED"
    assert "unlisted share unknown" in r["assessment"]


def test_loss_of_dominant_supplier_uses_each_reagents_own_top_country():
    res = compute_scenario(ROUTE_A, {"type": "dominant_supplier_loss"})
    assert reagent(res, "Reagent X")["target_country"] == "China"
    assert reagent(res, "Reagent Y")["target_country"] == "Germany"
    # 430 x 95% + 570 x 60% = 750.5
    assert route(res, "A")["affected_cost"] == pytest.approx(750.5)


def test_tariff_adds_cost_on_the_affected_share():
    res = compute_scenario(ROUTE_A, {"type": "tariff", "country": "China", "tariff_pct": 25})
    a = route(res, "A")
    assert a["added_cost"] == pytest.approx(408.5 * 0.25, abs=0.01)  # rounded to cents
    assert a["added_cost_pct"] == pytest.approx(10.21, abs=0.01)


def test_lead_time_increase_applies_to_exposed_supply():
    res = compute_scenario(ROUTE_A, {"type": "lead_time", "country": "China", "lead_time_increase_days": 90})
    x = reagent(res, "Reagent X")
    y = reagent(res, "Reagent Y")
    assert x["lead_time_after_affected_supply"] == 104
    assert x["lead_time_risk_after_affected_supply"] == 100.0
    assert y["lead_time_after_affected_supply"] == 14  # no China supply


def test_country_names_are_matched_across_source_spellings():
    items = [item("WITS reagent", 100.0, [("Korea, Rep.", 70.0), ("Japan", 30.0)], coverage="listed_only")]
    res = compute_scenario(items, {"type": "country_disruption", "country": "South Korea"})
    assert reagent(res, "WITS reagent")["exposure_share_pct"] == 70.0


def test_reagents_without_routes_are_grouped_together():
    items = [item("Manual", 50.0, [("China", 100.0)], routes={})]
    res = compute_scenario(items, {"type": "dominant_supplier_loss"})
    assert res["routes"][0]["route"] == ALL_REAGENTS_ROUTE


def test_invalid_scenarios_are_rejected():
    with pytest.raises(ValueError):
        compute_scenario(ROUTE_A, {"type": "forecast_war"})
    with pytest.raises(ValueError):
        compute_scenario(ROUTE_A, {"type": "country_disruption"})
