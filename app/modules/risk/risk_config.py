"""
Central, documented thresholds for the geographic-risk workflow.

Every number that turns trade shares into a tier, a wording choice, or a
scenario classification lives here so the rules can be reviewed (and changed)
in one place. See guide/08_risk_audit.md and guide/DATA_SOURCES.md.

All shares are percentages on a 0-100 scale.
"""

# -----------------------------------------------------------------
# Concentration risk (share of the reported supply held by the top
# supplier country, and by the top two combined when both are known)
# -----------------------------------------------------------------
CONCENTRATION_THRESHOLDS = {
    # HIGH: one country holds at least half of the reported supply ...
    "high_top1_pct": 50.0,
    # ... or the top two countries together hold at least this much.
    "high_top2_combined_pct": 80.0,
    # MEDIUM: the top country holds at least this much.
    "medium_top1_pct": 30.0,
}

# Ordering used when comparing tiers (UNKNOWN is deliberately not ranked
# against the others — unknown is neither safe nor dangerous).
CONCENTRATION_TIER_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}

# When every country other than the top supplier together holds less than
# this share, observed alternative sourcing is described as "limited".
LIMITED_ALTERNATIVES_SHARE_PCT = 10.0

# How many alternate countries to list in results (the count is always full).
MAX_ALTERNATE_COUNTRIES_LISTED = 5

# -----------------------------------------------------------------
# Trade-data context notes
# -----------------------------------------------------------------
# A change in total reported trade value of at least this much versus the
# previous complete year is called out in the provenance notes.
YOY_TOTAL_CHANGE_NOTE_PCT = 50.0

# -----------------------------------------------------------------
# Operational lead-time sub-score (existing formula, centralised so the
# scenario module reports the same numbers as the risk engine)
# -----------------------------------------------------------------
LEAD_TIME_FULL_RISK_DAYS = 30

# -----------------------------------------------------------------
# Scenario / shock analysis
# -----------------------------------------------------------------
# Route exposure tier from the share of the route's assessed reagent cost
# that a scenario touches.
SCENARIO_EXPOSURE_THRESHOLDS = {"high_pct": 25.0, "medium_pct": 10.0}

# A reagent with at least this share sourced from the affected country is
# described as having a "high dependency" on it; below the minimal share the
# exposure is described as "minimal".
SCENARIO_HIGH_DEPENDENCY_PCT = 50.0
SCENARIO_MINIMAL_EXPOSURE_PCT = 1.0

DEFAULT_TARIFF_PCT = 25.0
DEFAULT_LEAD_TIME_INCREASE_DAYS = 90

# -----------------------------------------------------------------
# Geography names
# -----------------------------------------------------------------
# Reporter names in trade data that are groupings of several economies, not
# single countries. They are never named as a "top supplier country".
AGGREGATE_REPORTERS = frozenset(
    {
        "world",
        "european union",
        "eu",
        "other asia, nes",
        "areas, nes",
        "other europe, nes",
        "other africa, nes",
        "other oceania, nes",
        "north america",
        "south asia",
        "east asia & pacific",
        "europe & central asia",
        "latin america & caribbean",
        "middle east & north africa",
        "sub-saharan africa",
    }
)

# Spelling differences between sources (USITC, WITS, country_stability.csv).
# Keys are lowercase variants; values are the canonical name used for matching.
COUNTRY_ALIASES = {
    "korea, rep.": "South Korea",
    "korea, republic of": "South Korea",
    "republic of korea": "South Korea",
    "korea": "South Korea",
    "russian federation": "Russia",
    "united states": "USA",
    "united states of america": "USA",
    "us": "USA",
    "u.s.": "USA",
    "turkiye": "Turkey",
    "türkiye": "Turkey",
    "chinese taipei": "Taiwan",
    "taiwan, china": "Taiwan",
    "viet nam": "Vietnam",
    "czechia": "Czech Republic",
    "czechia (czech republic)": "Czech Republic",
    "hong kong, china": "Hong Kong",
    "hong kong sar, china": "Hong Kong",
    "iran, islamic rep.": "Iran",
    "egypt, arab rep.": "Egypt",
    "slovak republic": "Slovakia",
    "united kingdom of great britain and northern ireland": "United Kingdom",
}


def canonical_country(name) -> str:
    """Return the canonical spelling of a country name for matching."""
    if name is None:
        return ""
    cleaned = " ".join(str(name).split())
    return COUNTRY_ALIASES.get(cleaned.lower(), cleaned)


def is_aggregate_reporter(name) -> bool:
    """True when a trade reporter is a grouping of economies, not one country."""
    if not name:
        return False
    return " ".join(str(name).split()).lower() in AGGREGATE_REPORTERS
