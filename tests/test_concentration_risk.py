"""Concentration risk tiers, explanations and alternative-sourcing wording."""

from app.modules.risk.concentration import (
    SHARE_OF_LISTED,
    SHARE_OF_TOTAL,
    assess_alternatives,
    assess_concentration,
)
from app.modules.risk.risk_config import CONCENTRATION_TIER_RANK


def suppliers(*pairs):
    return [{"country": c, "share_pct": s} for c, s in pairs]


def test_95_3_is_high_single_country():
    res = assess_concentration(
        suppliers(("China", 95.0), ("South Korea", 3.0)),
        basis_phrase="reported U.S. imports for this HS6 product",
    )
    assert res["tier"] == "HIGH"
    assert res["top_supplier_country"] == "China"
    assert res["top_supplier_share"] == 95.0
    assert res["second_supplier_country"] == "South Korea"
    assert res["second_supplier_share"] == 3.0
    assert res["explanation"].startswith(
        "95% of reported U.S. imports for this HS6 product originated from China."
    )
    assert "high single-country concentration" in res["explanation"]


def test_70_20_is_high():
    res = assess_concentration(suppliers(("Germany", 70.0), ("Japan", 20.0)))
    assert res["tier"] == "HIGH"
    assert res["top_two_combined_share"] == 90.0


def test_55_40_is_high():
    assert assess_concentration(suppliers(("Germany", 55.0), ("Japan", 40.0)))["tier"] == "HIGH"


def test_two_country_rule_triggers_high_below_50_percent():
    res = assess_concentration(suppliers(("Germany", 45.0), ("Japan", 40.0)))
    assert res["tier"] == "HIGH"
    assert "two-country" in res["explanation"]


def test_40_35_is_lower_than_the_95_case():
    moderate = assess_concentration(suppliers(("France", 40.0), ("Italy", 35.0)))
    severe = assess_concentration(suppliers(("China", 95.0), ("South Korea", 3.0)))
    assert moderate["tier"] == "MEDIUM"
    assert CONCENTRATION_TIER_RANK[moderate["tier"]] < CONCENTRATION_TIER_RANK[severe["tier"]]


def test_28_percent_top_supplier_is_low():
    res = assess_concentration(suppliers(("Brazil", 28.0), ("India", 20.0), ("USA", 15.0)))
    assert res["tier"] == "LOW"
    assert "relatively diversified" in res["explanation"]


def test_only_one_supplier_with_full_coverage_is_high():
    res = assess_concentration(suppliers(("Canada", 100.0)), total_country_count=1)
    assert res["tier"] == "HIGH"
    assert res["top_supplier_share"] == 100.0
    assert res["second_supplier_country"] is None
    assert "only origin country" in res["explanation"]


def test_single_listed_supplier_with_listed_only_shares_is_unknown():
    # A lone WITS-style row is 100% of the listed rows by construction.
    res = assess_concentration(suppliers(("China", 100.0)), share_basis=SHARE_OF_LISTED)
    assert res["tier"] == "UNKNOWN"
    assert res["top_supplier_share"] is None


def test_only_two_supplier_records_states_coverage():
    res = assess_concentration(suppliers(("China", 60.0), ("India", 25.0)))
    assert res["tier"] == "HIGH"
    assert res["supplier_countries_with_shares"] == 2
    assert (
        res["coverage_note"]
        == "Concentration assessment is based on the top 2 reported supplier countries."
    )


def test_unreported_second_supplier_is_not_assumed_zero():
    res = assess_concentration(suppliers(("Japan", 45.0)))
    assert res["tier"] == "MEDIUM"
    assert res["second_supplier_share"] is None
    assert "could be HIGH" in res["caveat"]


def test_missing_shares_are_unknown_not_scored():
    res = assess_concentration(suppliers(("China", None), ("India", None)))
    assert res["tier"] == "UNKNOWN"
    assert res["top_supplier_share"] is None
    assert "cannot be assessed" in res["explanation"]
    assert assess_concentration([])["tier"] == "UNKNOWN"


def test_regional_groupings_are_not_named_top_supplier():
    rows = [
        {"country": "Other Asia, nes", "share_pct": 60.0},
        {"country": "China", "share_pct": 25.0},
        {"country": "Japan", "share_pct": 15.0},
    ]
    res = assess_concentration(rows, share_basis=SHARE_OF_LISTED)
    assert res["top_supplier_country"] == "China"
    assert res["grouping_outranks_countries"] is True
    assert res["excluded_groupings"][0]["name"] == "Other Asia, nes"


def test_explanations_use_measured_condition_not_country_judgement():
    res = assess_concentration(suppliers(("China", 95.0), ("South Korea", 3.0)))
    text = res["explanation"].lower()
    for word in ("dangerous", "unsafe", "hostile", "unreliable"):
        assert word not in text


def test_thresholds_can_be_overridden_centrally():
    res = assess_concentration(
        suppliers(("Germany", 55.0), ("Japan", 10.0)),
        thresholds={"high_top1_pct": 60.0},
    )
    assert res["tier"] == "MEDIUM"


# -----------------------------------------------------------------
# Alternative sourcing / substitutability
# -----------------------------------------------------------------


def test_alternatives_are_trade_origins_not_qualified_suppliers():
    rows = suppliers(("China", 95.0), ("South Korea", 3.0), ("Germany", 2.0))
    conc = assess_concentration(rows, share_basis=SHARE_OF_TOTAL, total_country_count=3)
    alt = assess_alternatives(rows, conc, has_trade_data=True)
    assert [a["country"] for a in alt["alternate_supplier_countries"]] == ["South Korea", "Germany"]
    assert alt["alternate_country_count"] == 2
    assert alt["alternative_sourcing_basis"] == "observed_in_trade_data"
    assert alt["alternative_supply_known"] is False
    assert alt["alternative_chemistry_known"] is False
    assert alt["limited_alternatives"] is True
    assert "Alternative sourcing countries observed in trade data" in alt["summary"]
    assert "not verified or qualified suppliers" in alt["summary"]
    assert "qualified alternate suppliers exist" not in alt["summary"].lower()


def test_alternatives_without_trade_data_say_no_information():
    conc = assess_concentration([])
    alt = assess_alternatives([], conc, has_trade_data=False)
    assert alt["alternative_sourcing_basis"] == "no_information"
    assert alt["alternate_country_count"] is None
    assert alt["summary"].startswith("No information")


def test_substitutability_source_is_explicit():
    conc = assess_concentration(suppliers(("China", 95.0)))
    default = assess_alternatives([], conc, True, substitutability_score=5)
    user = assess_alternatives([], conc, True, 8, substitutability_source="user_input")
    assert default["substitutability_source"] == "default"
    assert default["substitutability_confidence"] == "none"
    assert user["substitutability_source"] == "user_input"
    assert user["substitutability_confidence"] == "user_asserted"
    assert user["substitutability_score"] == 8
