"""Trade-year selection: prefer the latest complete year over partial-year (YTD) data."""

import pytest

from app.modules.supply_chain import provider, usitc_ingest
from app.modules.supply_chain.provider import select_trade_year


def _full(total=100.0):
    return {"total": total, "period_type": "full_year"}


def _partial(total=10.0, label=None):
    return {"total": total, "period_type": "partial_year", "period_label": label}


# -----------------------------------------------------------------
# Pure selection logic
# -----------------------------------------------------------------


def test_complete_2025_beats_newer_partial_2026():
    sel = select_trade_year(
        {2024: _full(), 2025: _full(), 2026: _partial(label="YTD Jan 2026 (1 month)")}
    )
    assert sel["year"] == 2025
    assert sel["period_type"] == "full_year"
    assert sel["is_partial_year"] is False
    assert sel["reason"] == "latest_complete_year"
    # The skipped partial period is surfaced, not silently dropped.
    assert sel["newer_partial_year"] == 2026
    assert sel["newer_partial_label"] == "YTD Jan 2026 (1 month)"


def test_latest_of_multiple_complete_years():
    sel = select_trade_year({2023: _full(), 2025: _full(), 2024: _full()})
    assert sel["year"] == 2025
    assert sel["reason"] == "latest_complete_year"
    assert sel["newer_partial_year"] is None


def test_only_partial_year_is_used_and_labelled_partial():
    sel = select_trade_year({2026: _partial(label="YTD Jan 2026 (1 month)")})
    assert sel["year"] == 2026
    assert sel["is_partial_year"] is True
    assert sel["period_type"] == "partial_year"
    assert sel["reason"] == "no_complete_year_available"
    assert "YTD" in sel["period_label"]


def test_complete_year_without_data_falls_back_to_partial():
    sel = select_trade_year({2025: _full(total=0), 2026: _partial()})
    assert sel["year"] == 2026
    assert sel["is_partial_year"] is True


def test_explicit_ytd_request_uses_partial_year():
    sel = select_trade_year({2025: _full(), 2026: _partial()}, allow_partial=True)
    assert sel["year"] == 2026
    assert sel["reason"] == "explicit_ytd_requested"
    assert sel["is_partial_year"] is True


def test_explicit_ytd_request_without_newer_partial_keeps_complete_year():
    sel = select_trade_year({2025: _full()}, allow_partial=True)
    assert sel["year"] == 2025
    assert sel["reason"] == "latest_complete_year"


def test_requested_year_wins_when_it_has_data():
    sel = select_trade_year({2024: _full(), 2025: _full()}, requested_year=2024)
    assert sel["year"] == 2024
    assert sel["reason"] == "requested_year"


def test_requested_year_without_data_falls_back_and_says_so():
    sel = select_trade_year({2024: _full(), 2025: _full()}, requested_year=2019)
    assert sel["year"] == 2025
    assert sel["requested_year_unavailable"] is True


def test_malformed_years_are_ignored_safely():
    years = {
        "not-a-year": _full(),
        None: _full(),
        "2024.0": _full(),
        3025: _full(),  # out of range
        2025.5: _full(),  # not a calendar year
        True: _full(),
    }
    sel = select_trade_year(years)
    assert sel["year"] == 2024
    assert "not-a-year" in sel["ignored_years"]


def test_missing_coverage_information_is_a_labelled_fallback():
    # Neither full nor partial is known: never presented as a complete year.
    sel = select_trade_year({2025: {"total": 5.0}, 2024: {"total": 7.0, "period_type": "??"}})
    assert sel["year"] == 2025
    assert sel["period_type"] == "unknown"
    assert sel["is_partial_year"] is None
    assert sel["reason"] == "coverage_unknown_fallback"


def test_missing_coverage_does_not_beat_a_complete_year():
    sel = select_trade_year({2026: {"total": 5.0}, 2025: _full()})
    assert sel["year"] == 2025


@pytest.mark.parametrize("years", [{}, None, {2025: _full(total=0)}, {"x": _full()}])
def test_nothing_usable_returns_none(years):
    assert select_trade_year(years) is None


# -----------------------------------------------------------------
# USITC column parsing
# -----------------------------------------------------------------


def test_partial_period_column_is_described():
    period = usitc_ingest.describe_partial_period("January_to_january_year_2026")
    assert period["year"] == 2026
    assert period["months"] == 1
    assert period["label"] == "YTD Jan 2026 (1 month)"

    period = usitc_ingest.describe_partial_period("January to March 2026")
    assert period["months"] == 3
    assert period["label"] == "YTD Jan–Mar 2026 (3 months)"

    assert usitc_ingest.describe_partial_period("2025") is None


def test_year_columns_are_classified():
    full, partial = usitc_ingest._classify_year_columns(
        ["Country", "2024", "2025.0", "January_to_march_year_2026"]
    )
    assert set(full) == {2024, 2025}
    assert set(partial) == {2026}


# -----------------------------------------------------------------
# End-to-end through the provider with a synthetic USITC workbook
# -----------------------------------------------------------------


def test_provider_prefers_full_2025_over_january_2026(usitc_folder, write_usitc_workbook):
    # 2025: China 95 / South Korea 3 / Germany 2. Jan 2026: only Germany.
    write_usitc_workbook(
        usitc_folder / "imports.xlsx",
        [
            ("China", "291100", [80, 95, 0]),
            ("South Korea", "291100", [10, 3, 0]),
            ("Germany", "291100", [10, 2, 7]),
        ],
    )
    result = provider.get_origin_concentration("291100")
    assert result["status"] == "success"
    assert result["year"] == 2025
    assert result["period_label"] == "Full-year 2025"
    assert result["is_partial_year"] is False
    assert result["top_exporters"][0]["reporter"] == "China"
    assert result["concentration_top1_pct"] == pytest.approx(95.0)
    assert result["newer_partial_period_available"] == "YTD Jan 2026 (1 month)"

    ytd = provider.get_origin_concentration("291100", allow_partial=True)
    assert ytd["year"] == 2026
    assert ytd["is_partial_year"] is True
    assert ytd["top_exporters"][0]["reporter"] == "Germany"
    assert "partial-year" in ytd["data_quality_note"]


def test_provider_uses_partial_year_only_when_no_full_year(usitc_folder, write_usitc_workbook):
    write_usitc_workbook(
        usitc_folder / "imports.xlsx",
        [("Mexico", "291200", [0, 0, 40]), ("Canada", "291200", [0, 0, 60])],
    )
    result = provider.get_origin_concentration("291200")
    assert result["year"] == 2026
    assert result["is_partial_year"] is True
    assert result["year_selection_reason"] == "no_complete_year_available"
    assert "(partial)" not in result["source"]  # source stays the dataset name
    assert "YTD" in result["source_label"]
