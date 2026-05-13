from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
import json
import os
from datetime import datetime, timezone

def get_inchikey(smiles):
    mol = Chem.MolFromSmiles(smiles)
    if mol:
        return Chem.MolToInchiKey(mol)
    return None

# Seed data
seed_compounds = [
    {"name": "Terephthalic acid", "smiles": "O=C(O)c1ccc(C(=O)O)cc1", "hs6": "291736"},
    {"name": "Dimethyl terephthalate", "smiles": "COC(=O)c1ccc(C(=O)OC)cc1", "hs6": "291737"},
    {"name": "Ethylene glycol", "smiles": "OCCO", "hs6": "290531"},
    {"name": "Acrylic acid", "smiles": "C=CC(=O)O", "hs6": "291611"},
    {"name": "Phthalic anhydride", "smiles": "O=C1OC(=O)c2ccccc12", "hs6": "291735"},
]

mapping_path = "/home/sanjay/AV/synthesis-architect/database/compound_hs6_map.json"
os.makedirs(os.path.dirname(mapping_path), exist_ok=True)

mappings = {}
for c in seed_compounds:
    ikey = get_inchikey(c["smiles"])
    if ikey:
        mappings[ikey] = {
            "hs6_code": c["hs6"],
            "name_hint": c["name"],
            "added_at": datetime.now(timezone.utc).isoformat()
        }
    else:
        print(f"Warning: Could not compute InChIKey for {c['name']}")

data = {
    "schema_version": 1,
    "mappings": mappings
}

with open(mapping_path, 'w') as f:
    json.dump(data, f, indent=2)

print(f"Created mapping file at {mapping_path} with {len(mappings)} entries.")
