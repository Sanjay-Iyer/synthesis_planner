"""Central country-name normalisation across USITC, WITS, WGI and user input."""

import pytest

from app.modules.risk.risk_config import canonical_country, is_aggregate_reporter


@pytest.mark.parametrize(
    "variant, canonical",
    [
        ("Korea, Rep.", "South Korea"),
        ("South Korea", "South Korea"),
        ("Russian Federation", "Russia"),
        ("Viet Nam", "Vietnam"),
        ("Czechia", "Czech Republic"),
        ("Czechia (Czech Republic)", "Czech Republic"),  # USITC spelling
        ("Turkiye", "Turkey"),
        ("Türkiye", "Turkey"),
        ("Taiwan, China", "Taiwan"),
        ("Chinese Taipei", "Taiwan"),
        ("Hong Kong SAR, China", "Hong Kong"),
        ("United States", "USA"),
        ("Côte d`Ivoire", "Côte d'Ivoire"),  # USITC uses a backtick
        ("Cote d'Ivoire", "Côte d'Ivoire"),  # WGI spelling
        ("Bahamas, The", "Bahamas"),
        ("Congo, Dem. Rep.", "Democratic Republic of the Congo"),
        ("Venezuela, RB", "Venezuela"),
        ("Myanmar (Burma)", "Myanmar"),
        ("Naoero", "Nauru"),
        ("  korea,   rep. ", "South Korea"),  # spacing / case
    ],
)
def test_variants_map_to_one_canonical_name(variant, canonical):
    assert canonical_country(variant) == canonical


def test_canonicalisation_is_idempotent_and_keeps_unknown_names():
    for name in ("South Korea", "Côte d'Ivoire", "Germany", "Atlantis"):
        assert canonical_country(canonical_country(name)) == canonical_country(name)
    assert canonical_country("Atlantis") == "Atlantis"
    assert canonical_country(None) == ""
    assert canonical_country("   ") == ""


def test_groupings_are_not_countries():
    for name in ("European Union", "Other Asia, nes", "World", "Areas, nes"):
        assert is_aggregate_reporter(name)
    assert not is_aggregate_reporter("China")
