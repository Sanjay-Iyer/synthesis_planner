"""
Reagent -> HS6 resolution with provenance and mapping quality.

Trade data is looked up by HS6 code, so every concentration result is only as
good as the reagent -> HS6 mapping behind it. This module records *how* each
code was found and how much that match can be trusted:

  priority  match_method                 source                          exact  quality
  1         user_input                   user entry                      yes    HIGH
  2         cas                          reagent_mapping.csv             yes    HIGH
  3         inchikey                     compound_hs6_map.json           yes    HIGH
  4         compound_registry            compounds.hs6_code (by name)    no     MEDIUM
  5         compound_registry_inchikey   compounds.inchikey (by name)    no     MEDIUM
  6         name_hint                    compound_hs6_map.json hint      no     MEDIUM

A match to a broad / residual category ("NESOI", "Other ...") is downgraded to
LOW whatever the method: the code does not uniquely identify the reagent.

No LLM is involved; nothing here guesses a code.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from app.config import COMPOUND_HS6_MAP_PATH

QUALITY_ORDER = ["HIGH", "MEDIUM", "LOW"]

METHODS = {
    "user_input": {"source": "user entry", "exact": True, "quality": "HIGH"},
    "cas": {"source": "reagent_mapping.csv", "exact": True, "quality": "HIGH"},
    "inchikey": {"source": "compound_hs6_map.json", "exact": True, "quality": "HIGH"},
    "compound_registry": {
        "source": "synthesis_architect.db compounds.hs6_code (record matched by name)",
        "exact": False,
        "quality": "MEDIUM",
    },
    "compound_registry_inchikey": {
        "source": "compound_hs6_map.json via the InChIKey of a registry record matched by name",
        "exact": False,
        "quality": "MEDIUM",
    },
    "name_hint": {
        "source": "compound_hs6_map.json name_hint",
        "exact": False,
        "quality": "MEDIUM",
    },
}

METHOD_LABELS = {
    "user_input": "User-entered HS6",
    "cas": "CAS number",
    "inchikey": "Structure (InChIKey)",
    "compound_registry": "Compound registry record (name match)",
    "compound_registry_inchikey": "Registry InChIKey (name match)",
    "name_hint": "Name match",
}

# Purity / grade words dropped before an exact name comparison.
_QUALIFIERS = {
    "anhydrous", "purified", "polymer", "grade", "hplc", "acs", "reagent",
    "technical", "tech", "usp", "ep", "bp", "nf", "analytical", "ultrapure",
    "ultra", "pure", "extra", "dry", "puriss", "uhp", "lab", "laboratory",
}

_INCHIKEY_RE = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
_SELFIES_RE = re.compile(r"(\[[^\[\]]+\])+")
_BROAD_DESC_RE = re.compile(r"\bNESOI\b|\bn\.?e\.?s\b|not elsewhere|^\s*other\b", re.I)


# -----------------------------------------------------------------
# Identifiers
# -----------------------------------------------------------------


def clean_hs6(value) -> Optional[str]:
    """Digits-only, zero-padded HS6 code, or None (also for NaN/blank)."""
    if value is None:
        return None
    digits = "".join(filter(str.isdigit, str(value)))
    if not digits:
        return None
    return digits[:6].zfill(6)


def inchikey_from_structure(structure: Optional[str]) -> Optional[str]:
    """InChIKey from a SMILES, InChI, SELFIES or InChIKey string (RDKit)."""
    if not structure:
        return None
    text = str(structure).strip()
    if _INCHIKEY_RE.match(text):
        return text
    try:
        from rdkit import Chem, RDLogger

        RDLogger.DisableLog("rdApp.*")
    except ImportError:
        return None
    mol = None
    if text.startswith("InChI="):
        mol = Chem.MolFromInchi(text)
    else:
        # A string made only of [..] tokens is SELFIES; RDKit would otherwise
        # read "[O][C][C][O]" as a SMILES of radicals.
        if _SELFIES_RE.fullmatch(text):
            try:
                import selfies as sf

                decoded = sf.decoder(text)
                mol = Chem.MolFromSmiles(decoded) if decoded else None
            except Exception:
                mol = None
        if mol is None:
            mol = Chem.MolFromSmiles(text)
    return Chem.MolToInchiKey(mol) if mol is not None else None


def name_core(name: Optional[str]) -> str:
    """Lowercase name without parenthetical notes, grades or purity percentages."""
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", str(name or "").lower())
    text = re.sub(r"\d+(\.\d+)?\s*%", " ", text)
    words = [w for w in re.split(r"[\s,;]+", text) if w and w not in _QUALIFIERS]
    return " ".join(words)


# -----------------------------------------------------------------
# compound_hs6_map.json
# -----------------------------------------------------------------


def _load_hs6_map() -> dict:
    try:
        with open(COMPOUND_HS6_MAP_PATH, encoding="utf-8") as fh:
            return json.load(fh).get("mappings", {})
    except (OSError, json.JSONDecodeError):
        return {}


def hs6_for_inchikey(inchikey: Optional[str], mappings: Optional[dict] = None) -> Optional[str]:
    if not inchikey:
        return None
    mappings = _load_hs6_map() if mappings is None else mappings
    return clean_hs6((mappings.get(inchikey) or {}).get("hs6_code"))


def hs6_for_name(name: Optional[str], mappings: Optional[dict] = None) -> Optional[str]:
    """Exact name match (after removing grade qualifiers) against name hints.

    Substring matches are deliberately not accepted: "ethylene glycol dimethyl
    ether" must not resolve to ethylene glycol.
    """
    core = name_core(name)
    if not core:
        return None
    mappings = _load_hs6_map() if mappings is None else mappings
    for entry in mappings.values():
        if name_core(entry.get("name_hint")) == core:
            return clean_hs6(entry.get("hs6_code"))
    return None


# -----------------------------------------------------------------
# Resolution
# -----------------------------------------------------------------


def _resolution(hs6: Optional[str], method: Optional[str], note: Optional[str] = None) -> dict:
    info = METHODS.get(method or "", {})
    return {
        "hs6": hs6,
        "match_method": method,
        "match_label": METHOD_LABELS.get(method or ""),
        "source": info.get("source"),
        "exact": info.get("exact"),
        "mapping_quality": info.get("quality") if hs6 else None,
        "broad_category": None,
        "note": note,
    }


def resolve_hs6(
    name: str,
    cas: str = "",
    df_mapping=None,
    conn=None,
    columns: Optional[set] = None,
    hs6_input: Optional[str] = None,
    structure: Optional[str] = None,
) -> dict:
    """Resolve a reagent to an HS6 code; see the module docstring for priority.

    Also returns any origin stored alongside the CAS mapping / compound record
    (``mapped_origin``, ``db_primary_origin``, ``db_secondary_origin``).
    """
    name = (name or "").strip()
    cas = (cas or "").strip()
    found = _resolution(None, None)
    extras = {"mapped_origin": None, "db_primary_origin": None, "db_secondary_origin": None}

    user_hs6 = clean_hs6(hs6_input)
    if user_hs6:
        found = _resolution(user_hs6, "user_input", "User-entered HS6; not independently verified.")

    if cas and df_mapping is not None and not df_mapping.empty:
        rows = df_mapping[df_mapping["Reagent_CAS"].astype(str).str.strip() == cas]
        if not rows.empty:
            row = rows.iloc[0]
            origin = row.get("Primary_Origin")
            if isinstance(origin, str) and origin.strip():
                extras["mapped_origin"] = origin.strip()
            hs6 = clean_hs6(row.get("HS_Code"))
            if hs6 and not found["hs6"]:
                found = _resolution(hs6, "cas")

    mappings = _load_hs6_map()
    if not found["hs6"]:
        hs6 = hs6_for_inchikey(inchikey_from_structure(structure), mappings)
        if hs6:
            found = _resolution(hs6, "inchikey")

    if conn is not None and name:
        from app.modules.database.db import normalize_name

        cols = columns if columns is not None else set()
        wanted = [
            c
            for c in ("inchikey", "hs6_code", "primary_origin", "secondary_origin")
            if c in cols
        ]
        if "normalized_name" in cols and wanted:
            row = conn.execute(
                f"SELECT {', '.join(wanted)} FROM compounds WHERE normalized_name = ?",
                (normalize_name(name),),
            ).fetchone()
            if row:
                data = dict(zip(wanted, row))
                extras["db_primary_origin"] = data.get("primary_origin") or None
                extras["db_secondary_origin"] = data.get("secondary_origin") or None
                if not found["hs6"]:
                    db_hs6 = clean_hs6(data.get("hs6_code"))
                    if db_hs6:
                        found = _resolution(db_hs6, "compound_registry")
                    else:
                        mapped = hs6_for_inchikey(data.get("inchikey"), mappings)
                        if mapped:
                            found = _resolution(mapped, "compound_registry_inchikey")

    if not found["hs6"] and name:
        hinted = hs6_for_name(name, mappings)
        if hinted:
            found = _resolution(
                hinted, "name_hint", "Name match after removing grade/purity qualifiers."
            )

    return {**found, **extras}


def broad_category(hs6: Optional[str], description: Optional[str]) -> Optional[str]:
    """Reason text when the HS6 is a broad/residual category, else None."""
    if not hs6:
        return None
    if description:
        if _BROAD_DESC_RE.search(description):
            return f"Broad product category: '{description}'."
        return None
    if hs6.endswith("9"):
        return (
            "Likely a residual 'Other' subheading (HS6 ending in 9); no product "
            "description is available to confirm."
        )
    return None


def finalize_mapping(resolution: dict, description: Optional[str]) -> dict:
    """Apply the broad-category downgrade once the trade description is known."""
    result = dict(resolution)
    reason = broad_category(result.get("hs6"), description)
    result["broad_category"] = bool(reason) if result.get("hs6") else None
    result["description"] = description
    if reason:
        result["mapping_quality"] = "LOW"
        result["note"] = f"{result['note']} {reason}".strip() if result.get("note") else reason
    return result
