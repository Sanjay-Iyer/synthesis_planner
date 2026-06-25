"""Tests for the ELN procedure -> partial route draft extractor."""

from app.modules.extraction.service import extract_route_draft, REQUIRED_REAGENT_FIELDS

# Field sets must stay in sync with extraction/schemas.py
REAGENT_FIELDS = {
    "name",
    "mw",
    "equivalents",
    "mass",
    "mass_unit",
    "is_limiting",
    "smiles",
    "selfies",
    "cost_per_g",
    "pkg_size",
    "pkg_price",
    "needs_review",
}
STEP_FIELDS = {
    "step_id",
    "name",
    "product_mw",
    "reagents",
    "yield_percent",
    "temperature",
    "time",
    "procedure",
    "depends_on",
    "solvent_name",
    "solvent_volume",
    "solvent_volume_unit",
    "needs_review",
}
RESPONSE_FIELDS = {
    "steps",
    "target_molecule",
    "warnings",
    "extractor",
    "missing_required_count",
}


def _assert_schema(draft):
    assert set(draft) <= RESPONSE_FIELDS
    for step in draft["steps"]:
        assert set(step) <= STEP_FIELDS, set(step) - STEP_FIELDS
        for reagent in step["reagents"]:
            assert set(reagent) <= REAGENT_FIELDS, set(reagent) - REAGENT_FIELDS


SAMPLE = (
    "To a stirred solution of aniline (5.0 g, 54 mmol, 1.0 equiv) in 50 mL of THF "
    "was added acetic anhydride (6.6 g, 65 mmol, 1.2 equiv) at room temperature. "
    "The mixture was heated to 80 C and stirred for 4 h. Isolated in 88% yield."
)


def test_schema_shape_is_valid():
    _assert_schema(extract_route_draft(SAMPLE))


def test_reagent_names_are_cleaned():
    step = extract_route_draft(SAMPLE)["steps"][0]
    names = [r["name"] for r in step["reagents"]]
    assert names == ["aniline", "acetic anhydride"]


def test_solvent_temp_time_yield_captured():
    step = extract_route_draft(SAMPLE)["steps"][0]
    assert step["solvent_name"] == "THF"
    assert step["solvent_volume"] == 50.0 and step["solvent_volume_unit"] == "mL"
    assert step["temperature"] == "80C"
    assert step["time"] == "4 h"
    assert step["yield_percent"] == 88.0


def test_missing_mw_is_flagged_for_review():
    # MW is never stated in prose -> must appear in needs_review for every reagent.
    step = extract_route_draft(SAMPLE)["steps"][0]
    for r in step["reagents"]:
        assert "mw" in r["needs_review"]
    assert "mw" in REQUIRED_REAGENT_FIELDS


def test_first_massed_reagent_marked_limiting():
    step = extract_route_draft(SAMPLE)["steps"][0]
    limiting = [r for r in step["reagents"] if r["is_limiting"]]
    assert len(limiting) == 1 and limiting[0]["name"] == "aniline"
    assert limiting[0]["equivalents"] == 1.0


def test_sparse_text_yields_editable_scaffold():
    draft = extract_route_draft("A general amide coupling was performed.")
    _assert_schema(draft)
    assert len(draft["steps"]) == 1
    # one empty placeholder reagent so the Planner shows an editable row
    assert len(draft["steps"][0]["reagents"]) == 1
    assert draft["warnings"]


def test_empty_input_returns_one_empty_step():
    draft = extract_route_draft("")
    _assert_schema(draft)
    assert len(draft["steps"]) == 1
    assert draft["missing_required_count"] > 0


def test_explicit_multistep_with_dependency():
    draft = extract_route_draft(
        "Step 1. Mix NaH (2.0 g) in THF.\nStep 2. Add water (10 mL) to the product."
    )
    assert len(draft["steps"]) == 2
    assert draft["steps"][1]["depends_on"] == [1]
