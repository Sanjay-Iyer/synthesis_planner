"""HS6 resolution: priority, provenance and mapping-quality labels."""

import sqlite3

import pandas as pd
import pytest

from app.modules.risk import hs6_mapping
from app.modules.risk.hs6_mapping import (
    broad_category,
    finalize_mapping,
    inchikey_from_structure,
    name_core,
    resolve_hs6,
)

MAP = {
    "KKEYFWRCBNTPAC-UHFFFAOYSA-N": {"hs6_code": "291736", "name_hint": "Terephthalic acid"},
    "LYCAIKOWRPUZTN-UHFFFAOYSA-N": {"hs6_code": "290531", "name_hint": "Ethylene glycol"},
}
CAS = pd.DataFrame(
    {"Reagent_CAS": ["100-21-0"], "HS_Code": ["2917.36"], "Primary_Origin": ["Thailand"]}
)


@pytest.fixture(autouse=True)
def fixed_map(monkeypatch):
    monkeypatch.setattr(hs6_mapping, "_load_hs6_map", lambda: MAP)


def registry(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE compounds (normalized_name TEXT, inchikey TEXT, hs6_code TEXT, "
        "primary_origin TEXT, secondary_origin TEXT)"
    )
    conn.executemany("INSERT INTO compounds VALUES (?, ?, ?, ?, ?)", rows)
    cols = {"normalized_name", "inchikey", "hs6_code", "primary_origin", "secondary_origin"}
    return conn, cols


def test_cas_mapping_is_exact_and_high():
    res = resolve_hs6("anything", cas="100-21-0", df_mapping=CAS)
    assert res["hs6"] == "291736"
    assert res["match_method"] == "cas"
    assert res["mapping_quality"] == "HIGH"
    assert res["exact"] is True
    assert res["source"] == "reagent_mapping.csv"
    assert res["mapped_origin"] == "Thailand"


def test_inchikey_mapping_from_smiles_is_exact_and_high():
    res = resolve_hs6("TPA, polymer grade", structure="O=C(O)c1ccc(C(=O)O)cc1")
    assert res["hs6"] == "291736"
    assert res["match_method"] == "inchikey"
    assert res["mapping_quality"] == "HIGH"
    assert res["exact"] is True


def test_structure_identifiers_resolve_to_inchikey():
    key = "LYCAIKOWRPUZTN-UHFFFAOYSA-N"
    assert inchikey_from_structure("OCCO") == key
    assert inchikey_from_structure("[O][C][C][O]") == key  # SELFIES, not radicals
    assert inchikey_from_structure(key) == key
    assert inchikey_from_structure("not a molecule ###") is None


def test_name_based_mapping_is_medium_and_not_exact():
    res = resolve_hs6("Ethylene glycol (Anhydrous)")
    assert res["hs6"] == "290531"
    assert res["match_method"] == "name_hint"
    assert res["mapping_quality"] == "MEDIUM"
    assert res["exact"] is False


def test_name_match_rejects_different_compounds_sharing_a_prefix():
    assert resolve_hs6("Ethylene glycol dimethyl ether")["hs6"] is None
    assert name_core("Terephthalic acid (Polymer Grade, 99.5%)") == "terephthalic acid"


def test_registry_record_matched_by_name_is_medium():
    conn, cols = registry([("germaniumdioxidecatalyst", None, "282560", None, None)])
    res = resolve_hs6("Germanium dioxide catalyst", conn=conn, columns=cols)
    assert res["hs6"] == "282560"
    assert res["match_method"] == "compound_registry"
    assert res["mapping_quality"] == "MEDIUM"
    assert res["exact"] is False


def test_missing_mapping_returns_no_code_and_no_quality():
    res = resolve_hs6("Mystery catalyst XYZ")
    assert res["hs6"] is None
    assert res["match_method"] is None
    assert res["mapping_quality"] is None


def test_user_entered_hs6_takes_priority():
    res = resolve_hs6("anything", cas="100-21-0", df_mapping=CAS, hs6_input="2905.31")
    assert res["hs6"] == "290531"
    assert res["match_method"] == "user_input"
    assert "not independently verified" in res["note"]


def test_broad_category_is_labelled_low():
    res = finalize_mapping(
        resolve_hs6("Ethylene glycol"), "SALTS OF ACETIC ACID, NESOI"
    )
    assert res["mapping_quality"] == "LOW"
    assert res["broad_category"] is True
    assert "Broad product category" in res["note"]


def test_residual_code_without_description_is_flagged():
    assert "residual" in broad_category("381239", None)
    assert broad_category("291736", None) is None
    assert broad_category("291736", "TEREPHTHALIC ACID AND ITS SALTS") is None
    assert broad_category("291590", "Other saturated acyclic monocarboxylic acids") is not None


def test_specific_category_keeps_its_quality():
    res = finalize_mapping(resolve_hs6("x", structure="OCCO"), "ETHYLENE GLYCOL (ETHANEDIOL)")
    assert res["mapping_quality"] == "HIGH"
    assert res["broad_category"] is False
