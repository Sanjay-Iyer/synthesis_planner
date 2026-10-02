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
# Composite risk index (legacy "Risk Index" column)
# -----------------------------------------------------------------
# Weighted mean of the components that are available. Concentration is NOT a
# component: it is reported as its own result. A component that cannot be
# assessed (e.g. geographic when the origin or its WGI score is unknown) is
# left out and the remaining weights are renormalised; the result lists the
# missing components instead of substituting a value.
COMPOSITE_WEIGHTS = {
    "geographic": 0.30,
    "operational": 0.20,
    "regulatory": 0.30,
    "economic": 0.20,
}

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

# Spelling differences between sources: USITC DataWeb, WITS / World Bank (also
# used by WGI), and user input. Canonical names follow USITC where possible
# because trade data drives origins. Keys are matched after _match_key()
# (lowercase, accents removed, backticks -> apostrophes, single spaces).
COUNTRY_ALIASES = {
    # World Bank / WITS / WGI style -> canonical
    "korea, rep.": "South Korea",
    "korea, republic of": "South Korea",
    "republic of korea": "South Korea",
    "korea": "South Korea",
    "korea, dem. people's rep.": "North Korea",
    "russian federation": "Russia",
    "united states": "USA",
    "united states of america": "USA",
    "us": "USA",
    "u.s.": "USA",
    "turkiye": "Turkey",
    "chinese taipei": "Taiwan",
    "taiwan, china": "Taiwan",
    "viet nam": "Vietnam",
    "czechia": "Czech Republic",
    "czechia (czech republic)": "Czech Republic",
    "hong kong, china": "Hong Kong",
    "hong kong sar, china": "Hong Kong",
    "macao sar, china": "Macau",
    "macao": "Macau",
    "iran, islamic rep.": "Iran",
    "egypt, arab rep.": "Egypt",
    "slovak republic": "Slovakia",
    "united kingdom of great britain and northern ireland": "United Kingdom",
    "bahamas, the": "Bahamas",
    "gambia, the": "Gambia",
    "brunei darussalam": "Brunei",
    "cote d'ivoire": "Côte d'Ivoire",
    "curacao": "Curaçao",
    "congo, dem. rep.": "Democratic Republic of the Congo",
    "congo, rep.": "Republic of the Congo",
    "eswatini (swaziland)": "Eswatini",
    "swaziland": "Eswatini",
    "kyrgyz republic": "Kyrgyzstan",
    "lao pdr": "Laos",
    "micronesia, fed. sts.": "Micronesia",
    "myanmar (burma)": "Myanmar",
    "burma": "Myanmar",
    "naoero": "Nauru",
    "st. kitts and nevis": "Saint Kitts and Nevis",
    "st. lucia": "Saint Lucia",
    "st. vincent and the grenadines": "Saint Vincent and the Grenadines",
    "somalia, fed. rep.": "Somalia",
    "syrian arab republic": "Syria",
    "sao tome and principe": "São Tomé and Príncipe",
    "venezuela, rb": "Venezuela",
    "yemen, rep.": "Yemen",
    "puerto rico (us)": "Puerto Rico",
    "virgin islands (u.s.)": "U.S. Virgin Islands",
    "north macedonia": "North Macedonia",
    "macedonia": "North Macedonia",
    # WGI reports the West Bank and Gaza together; USITC lists them separately.
    "west bank": "West Bank and Gaza",
    "gaza strip": "West Bank and Gaza",
}


def _match_key(name) -> str:
    """Lowercase, accent-free, single-spaced key for alias lookups."""
    import unicodedata

    text = " ".join(str(name).replace("`", "'").replace("’", "'").split())
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def canonical_country(name) -> str:
    """Return the canonical spelling of a country name for matching.

    Every module (stability lookup, scenarios, concentration) matches countries
    through this function, so a new source spelling only needs an alias here.
    """
    if name is None:
        return ""
    cleaned = " ".join(str(name).split())
    if not cleaned:
        return ""
    return COUNTRY_ALIASES.get(_match_key(cleaned), cleaned)


def is_aggregate_reporter(name) -> bool:
    """True when a trade reporter is a grouping of economies, not one country."""
    if not name:
        return False
    return " ".join(str(name).split()).lower() in AGGREGATE_REPORTERS
