import sys
import json
from pathlib import Path
from datetime import datetime, timezone

# Make the `app` package importable when run as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from app.config import COMPOUND_HS6_MAP_PATH


def get_inchikey(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol:
        return Chem.MolToInchiKey(mol)
    return None


# Seed data
seed_compounds = [
    {"name": "Terephthalic acid", "smiles": "O=C(O)c1ccc(C(=O)O)cc1", "hs6": "291736"},
    {
        "name": "Dimethyl terephthalate",
        "smiles": "COC(=O)c1ccc(C(=O)OC)cc1",
        "hs6": "291737",
    },
    {"name": "Ethylene glycol", "smiles": "OCCO", "hs6": "290531"},
    {"name": "Acrylic acid", "smiles": "C=CC(=O)O", "hs6": "291611"},
    {"name": "Phthalic anhydride", "smiles": "O=C1OC(=O)c2ccccc12", "hs6": "291735"},
]

mapping_path = COMPOUND_HS6_MAP_PATH
mapping_path.parent.mkdir(parents=True, exist_ok=True)

mappings = {}
for c in seed_compounds:
    ikey = get_inchikey(c["smiles"])
    if ikey:
        mappings[ikey] = {
            "hs6_code": c["hs6"],
            "name_hint": c["name"],
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
    else:
        print(f"Warning: Could not compute InChIKey for {c['name']}")

data = {"schema_version": 1, "mappings": mappings}

with open(mapping_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print(f"Created mapping file at {mapping_path} with {len(mappings)} entries.")
