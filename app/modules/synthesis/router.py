"""
Synthesis Router — API endpoints for stoichiometry and cost analysis.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests
import re
try:
    import selfies as sf
except ImportError:
    sf = None
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors
except ImportError:
    Chem = None

from .engine import SynthesisProject, calculate_engine, audit_optimization

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])


@router.post("/estimate")
def estimate_synthesis(project: SynthesisProject):
    """Scale-up cost estimation for a synthesis route."""
    return calculate_engine(project)


@router.post("/audit")
def run_audit(project: SynthesisProject):
    """Yield sensitivity audit — find where to optimize."""
    return audit_optimization(project)


# =================================================================
# MOLECULE UTILITIES
# =================================================================

class MoleculeInput(BaseModel):
    string_input: str

@router.post("/molecule-name")
def get_molecule_name(data: MoleculeInput):
    """Get molecule name from SMILES or SELFIES."""
    val = data.string_input.strip()
    if not val:
        raise HTTPException(status_code=400, detail="Empty input string")
    
    # If SELFIES (contains [ and ]), try converting to SMILES
    smiles_str = val
    if "[" in val and "]" in val and sf is not None:
        try:
            smiles_str = sf.decoder(val)
        except Exception:
            pass # fallback to trying it as SMILES

    # Query PubChem PUG REST
    # URL format: https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{smiles}/synonyms/JSON
    try:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{smiles_str}/synonyms/JSON"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            info = resp.json()
            syns = info.get("InformationList", {}).get("Information", [{}])[0].get("Synonym", [])
            if syns:
                return {"name": syns[0], "smiles": smiles_str}
        
        # Fallback to CID lookup then name if synonym endpoint fails
        cid_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{smiles_str}/cids/JSON"
        cid_resp = requests.get(cid_url, timeout=5)
        if cid_resp.status_code == 200:
            cids = cid_resp.json().get("IdentifierList", {}).get("CID", [])
            if cids:
                return {"name": f"PubChem CID {cids[0]}", "smiles": smiles_str}
    except Exception as e:
        pass
        
    return {"name": "Unknown Molecule", "smiles": smiles_str}


PERIODIC_TABLE = {
    'H': 1.008, 'C': 12.011, 'N': 14.007, 'O': 15.999, 'P': 30.974, 'S': 32.065,
    'F': 18.998, 'Cl': 35.45, 'Br': 79.904, 'I': 126.904, 'B': 10.81, 'Si': 28.085,
    'Na': 22.990, 'K': 39.098, 'Li': 6.94, 'Mg': 24.305, 'Ca': 40.078,
}

@router.post("/molecular-weight")
def get_molecular_weight(data: MoleculeInput):
    """Calculate MW from a SMILES or chemical formula."""
    val = data.string_input.strip()
    if not val:
        raise HTTPException(status_code=400, detail="Empty input string")

    # If SELFIES, decode it first
    if "[" in val and "]" in val and sf is not None:
        try:
            val = sf.decoder(val)
        except Exception:
            pass

    # Try RDKit first if it's a valid SMILES
    if Chem is not None:
        mol = Chem.MolFromSmiles(val)
        if mol:
            return {"mw": round(Descriptors.MolWt(mol), 3), "method": "RDKit (Exact MolWt)"}

    # Fallback to elemental character parsing (Periodic Table sum)
    matches = re.findall(r'([A-Z][a-z]*)(\d*)', val)
    mw = 0.0
    elements_found = []
    for element, count in matches:
        if element in PERIODIC_TABLE:
            c = int(count) if count else 1
            mw += PERIODIC_TABLE[element] * c
            elements_found.append(f"{element}{c if c>1 else ''}")
    
    if mw > 0:
        return {"mw": round(mw, 3), "method": "Formula String Parser"}
        
    return {"mw": 0.0, "method": "Unrecognized Input"}

