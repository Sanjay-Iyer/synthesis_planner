import pytest
from app.modules.risk.engine import lookup_suggested_origins

def test_lookup_suggested_origins_by_name():
    """Verify that Terephthalic acid is matched to its HS6 code and origins."""
    reagents = [{"name": "Terephthalic acid (Polymer Grade)", "cas": ""}]
    results = lookup_suggested_origins(reagents)
    
    assert len(results) == 1
    assert results[0]["hs6"] == "291736"
    # The live-scanned USITC import dataset takes priority over the older WITS
    # export fallback. Its seeded 2026 U.S. origin record is Mexico.
    assert results[0]["primary"] == "Mexico"

def test_lookup_suggested_origins_by_cas():
    """Verify that CAS lookup works for suggestions."""
    reagents = [{"name": "Ethylene Glycol", "cas": "107-21-1"}]
    results = lookup_suggested_origins(reagents)
    
    assert len(results) == 1
    # 107-21-1 -> 290531
    assert results[0]["hs6"] == "290531"
    # Need to check top exporter for 290531 in wits_exports.json
    assert results[0]["primary"] != "Unknown"

def test_lookup_suggested_origins_mixed():
    """Verify mixed name and CAS lookups."""
    reagents = [
        {"name": "Ethylene glycol (Purified)", "cas": ""},
        {"name": "Acrylic acid", "cas": "79-10-7"}
    ]
    results = lookup_suggested_origins(reagents)
    
    assert len(results) == 2
    assert results[0]["hs6"] == "290531"
    assert results[1]["hs6"] == "291611"
    assert results[1]["primary"] != "Unknown"
