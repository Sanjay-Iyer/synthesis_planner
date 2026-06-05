import sqlite3
import uuid
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
import logging

try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

DB_DIR = Path("/home/sanjay/AV/synthesis-architect/database")
DB_PATH = DB_DIR / "synthesis_architect.db"

logger = logging.getLogger(__name__)

def get_utc_now() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()

def normalize_name(name: str) -> str:
    """Normalize chemical name for comparison."""
    if not name:
        return ""
    # Remove special characters, spaces, and lowercase
    return re.sub(r'[^a-zA-Z0-9]', '', name).lower()

def connect_db():
    """Establish a connection to the SQLite database."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database schema."""
    conn = connect_db()
    cursor = conn.cursor()

    # Compounds Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compounds (
        uuid TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        normalized_name TEXT,
        smiles TEXT,
        canonical_smiles TEXT,
        selfies TEXT,
        inchikey TEXT,
        formula TEXT,
        mw REAL,
        exact_mw REAL,
        cas TEXT,
        hs6_code TEXT,
        primary_origin TEXT,
        secondary_origin TEXT,
        compound_type TEXT,
        is_defined_structure INTEGER DEFAULT 1,
        dedupe_basis TEXT,
        dedupe_confidence TEXT,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        notes TEXT
    )
    """)

    # --- Schema Migrations ---
    cursor.execute("PRAGMA table_info(compounds)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "hs6_code" not in columns:
        try:
            cursor.execute("ALTER TABLE compounds ADD COLUMN hs6_code TEXT")
        except sqlite3.OperationalError:
            pass
            
    if "primary_origin" not in columns:
        try:
            cursor.execute("ALTER TABLE compounds ADD COLUMN primary_origin TEXT")
        except sqlite3.OperationalError:
            pass

    if "secondary_origin" not in columns:
        try:
            cursor.execute("ALTER TABLE compounds ADD COLUMN secondary_origin TEXT")
        except sqlite3.OperationalError:
            pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compounds_hs6_code ON compounds(hs6_code)")

    # Partial unique indexes for SQLite 3.9+
    try:
        cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_compounds_canonical_smiles 
        ON compounds(canonical_smiles) 
        WHERE canonical_smiles IS NOT NULL AND canonical_smiles != ''
        """)
        cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_compounds_inchikey 
        ON compounds(inchikey) 
        WHERE inchikey IS NOT NULL AND inchikey != ''
        """)
    except sqlite3.OperationalError:
        # Fallback for older SQLite versions if needed, though most modern ones support it
        pass

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compounds_norm_name ON compounds(normalized_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compounds_smiles ON compounds(smiles)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_compounds_selfies ON compounds(selfies)")

    # Routes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS routes (
        uuid TEXT PRIMARY KEY,
        route_label TEXT NOT NULL,
        target_molecule TEXT,
        source_file TEXT,
        route_hash TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        raw_route_json TEXT
    )
    """)

    # Route Steps Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS route_steps (
        uuid TEXT PRIMARY KEY,
        route_uuid TEXT NOT NULL,
        step_number INTEGER NOT NULL,
        name TEXT,
        product_mw REAL,
        temperature TEXT,
        time TEXT,
        procedure TEXT,
        yield_percent REAL,
        molarity REAL,
        solvent_name TEXT,
        solvent_volume REAL,
        solvent_volume_unit TEXT,
        solvent_volume_l REAL,
        solvent_density REAL,
        solvent_bottle_l REAL,
        solvent_bottle_price REAL,
        solvent_price_per_l REAL,
        depends_on_json TEXT,
        raw_step_json TEXT,
        FOREIGN KEY(route_uuid) REFERENCES routes(uuid) ON DELETE CASCADE
    )
    """)

    # Step Reagents Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS step_reagents (
        uuid TEXT PRIMARY KEY,
        step_uuid TEXT NOT NULL,
        route_uuid TEXT NOT NULL,
        compound_uuid TEXT,
        name TEXT NOT NULL,
        role TEXT,
        smiles TEXT,
        selfies TEXT,
        mw REAL,
        pkg_size REAL,
        pkg_price REAL,
        cost_per_g REAL,
        moles REAL,
        mass REAL,
        mass_unit TEXT,
        is_limiting INTEGER,
        raw_reagent_json TEXT,
        FOREIGN KEY(step_uuid) REFERENCES route_steps(uuid) ON DELETE CASCADE,
        FOREIGN KEY(route_uuid) REFERENCES routes(uuid) ON DELETE CASCADE,
        FOREIGN KEY(compound_uuid) REFERENCES compounds(uuid)
    )
    """)

    # Analysis Runs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analysis_runs (
        uuid TEXT PRIMARY KEY,
        route_uuid TEXT NOT NULL,
        target_mass_kg REAL,
        total_cost REAL,
        cost_per_kg REAL,
        e_factor REAL,
        overall_yield_percent REAL,
        created_at TEXT NOT NULL,
        raw_results_json TEXT,
        FOREIGN KEY(route_uuid) REFERENCES routes(uuid) ON DELETE CASCADE
    )
    """)

    # Metadata Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)

    # Insert version
    cursor.execute("INSERT OR IGNORE INTO metadata (key, value) VALUES ('database_version', '1.0')")

    conn.commit()
    conn.close()

def canonicalize_smiles(smiles: Optional[str]) -> dict:
    """Canonicalize SMILES and extract molecular properties."""
    result = {
        "canonical_smiles": None,
        "inchikey": None,
        "formula": None,
        "exact_mw": None,
        "mw": None,
        "error": None
    }
    
    if not smiles:
        return result
        
    if RDKIT_AVAILABLE:
        try:
            mol = Chem.MolFromSmiles(smiles)
            if mol:
                result["canonical_smiles"] = Chem.MolToSmiles(mol, isomericSmiles=True)
                result["inchikey"] = rdMolDescriptors.CalcInchiKey(mol)
                result["formula"] = rdMolDescriptors.CalcMolecularFormula(mol)
                result["exact_mw"] = Descriptors.ExactMolWt(mol)
                result["mw"] = Descriptors.MolWt(mol)
            else:
                result["error"] = "Invalid SMILES string"
                result["canonical_smiles"] = smiles # Fallback
        except Exception as e:
            result["error"] = str(e)
            result["canonical_smiles"] = smiles # Fallback
    else:
        result["canonical_smiles"] = smiles
        
    return result

def is_ambiguous(name: str, smiles: Optional[str], selfies: Optional[str], inchikey: Optional[str]) -> bool:
    """Determine if a compound definition is ambiguous."""
    if smiles or selfies or inchikey:
        return False
        
    vague_patterns = [
        r"intermediate", r"oligomer", r"stabilizer", r"slurry", 
        r"neat", r"atmosphere", r"catalyst", r"unknown", r"mixture"
    ]
    name_lower = name.lower()
    for pattern in vague_patterns:
        if re.search(pattern, name_lower):
            return True
            
    if len(name) < 3:
        return True
        
    return False

def find_existing_compound(conn, compound_data: dict) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Find existing compound using multi-tier matching."""
    cursor = conn.cursor()
    
    can_smiles = compound_data.get("canonical_smiles")
    inchikey = compound_data.get("inchikey")
    selfies = compound_data.get("selfies")
    norm_name = normalize_name(compound_data.get("name", ""))
    
    # 1. Canonical SMILES
    if can_smiles:
        cursor.execute("SELECT uuid FROM compounds WHERE canonical_smiles = ?", (can_smiles,))
        row = cursor.fetchone()
        if row: return row["uuid"], "canonical_smiles", "high"
        
    # 2. InChIKey
    if inchikey:
        cursor.execute("SELECT uuid FROM compounds WHERE inchikey = ?", (inchikey,))
        row = cursor.fetchone()
        if row: return row["uuid"], "inchikey", "high"
        
    # 3. SELFIES
    if selfies:
        cursor.execute("SELECT uuid FROM compounds WHERE selfies = ?", (selfies,))
        row = cursor.fetchone()
        if row: return row["uuid"], "selfies", "medium"
        
    # 4. Normalized Name
    if norm_name:
        cursor.execute("SELECT uuid FROM compounds WHERE normalized_name = ?", (norm_name,))
        row = cursor.fetchone()
        if row: return row["uuid"], "normalized_name", "low"
        
    return None, None, "none"

def upsert_compound(conn, compound_input: Any, route_uuid: str = None) -> dict:
    """Insert or update a compound and return its status."""
    cursor = conn.cursor()
    
    name = compound_input.name
    smiles = compound_input.smiles
    selfies = compound_input.selfies
    
    # Extract properties
    props = canonicalize_smiles(smiles)
    inchikey = props["inchikey"]
    can_smiles = props["canonical_smiles"]
    
    compound_data = {
        "name": name,
        "smiles": smiles,
        "canonical_smiles": can_smiles,
        "selfies": selfies,
        "inchikey": inchikey
    }
    
    existing_uuid, basis, confidence = find_existing_compound(conn, compound_data)
    now = get_utc_now()
    
    ambiguous = is_ambiguous(name, can_smiles, selfies, inchikey)
    
    if existing_uuid:
        # Update last_seen
        cursor.execute("UPDATE compounds SET last_seen = ? WHERE uuid = ?", (now, existing_uuid))
        return {
            "uuid": existing_uuid,
            "status": "updated",
            "dedupe_basis": basis,
            "dedupe_confidence": confidence,
            "ambiguous": ambiguous
        }
    else:
        new_uuid = str(uuid.uuid4())
        norm_name = normalize_name(name)
        
        cursor.execute("""
        INSERT INTO compounds (
            uuid, name, normalized_name, smiles, canonical_smiles, selfies, 
            inchikey, formula, mw, exact_mw, is_defined_structure, 
            dedupe_basis, dedupe_confidence, first_seen, last_seen
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_uuid, name, norm_name, smiles, can_smiles, selfies,
            inchikey, props["formula"], props["mw"] or compound_input.mw, props["exact_mw"],
            0 if ambiguous else 1, "none", "none", now, now
        ))
        
        return {
            "uuid": new_uuid,
            "status": "new",
            "dedupe_basis": "none",
            "dedupe_confidence": "high" if not ambiguous else "low",
            "ambiguous": ambiguous
        }

def compute_route_hash(route_data: dict, target_molecule: str) -> str:
    """Compute a SHA256 hash for the route definition."""
    # Build a stable representation
    parts = [target_molecule]
    
    for step in route_data.get("steps", []):
        parts.append(step.get("name", ""))
        parts.append(str(step.get("step_id", "")))
        parts.append(str(step.get("yield_percent", "")))
        parts.append(str(step.get("temperature", "")))
        parts.append(str(step.get("time", "")))
        
        for reagent in step.get("reagents", []):
            parts.append(reagent.get("name", ""))
            parts.append(str(reagent.get("mw", "")))
            parts.append(str(reagent.get("moles", "")))
            parts.append(str(reagent.get("mass", "")))
            parts.append(reagent.get("smiles", "") or "")
            parts.append(reagent.get("selfies", "") or "")
            
    stable_str = "|".join(parts)
    return hashlib.sha256(stable_str.encode('utf-8')).hexdigest()

def save_route_transaction(conn, request: Any) -> dict:
    """Save route, steps, reagents, and analysis run in a transaction."""
    cursor = conn.cursor()
    now = get_utc_now()
    
    # 1. Compute Route Hash
    route_json = request.route.model_dump()
    route_hash = compute_route_hash(route_json, request.target_molecule)
    
    # 2. Check for existing route
    cursor.execute("SELECT uuid FROM routes WHERE route_hash = ?", (route_hash,))
    row = cursor.fetchone()
    
    if row:
        route_uuid = row["uuid"]
        cursor.execute("UPDATE routes SET updated_at = ? WHERE uuid = ?", (now, route_uuid))
    else:
        route_uuid = str(uuid.uuid4())
        cursor.execute("""
        INSERT INTO routes (uuid, route_label, target_molecule, source_file, route_hash, created_at, updated_at, raw_route_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            route_uuid, request.route_label, request.target_molecule, request.source_file,
            route_hash, now, now, json.dumps(route_json)
        ))
        
        # 3. Save Steps and Reagents (only if new route)
        for step_idx, step in enumerate(request.route.steps):
            step_uuid = str(uuid.uuid4())
            step_data = step.model_dump()
            
            cursor.execute("""
            INSERT INTO route_steps (
                uuid, route_uuid, step_number, name, product_mw, temperature, time, procedure, 
                yield_percent, molarity, solvent_name, solvent_volume, solvent_volume_unit, 
                solvent_volume_l, solvent_density, solvent_bottle_l, solvent_bottle_price, 
                solvent_price_per_l, depends_on_json, raw_step_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                step_uuid, route_uuid, step.step_id, step.name, step.product_mw, step.temperature, step.time, 
                step.procedure, step.yield_percent, step.molarity, step.solvent_name, step.solvent_volume, 
                step.solvent_volume_unit, step.solvent_volume_l, step.solvent_density, step.solvent_bottle_l, 
                step.solvent_bottle_price, step.solvent_price_per_l, json.dumps(step.depends_on), json.dumps(step_data)
            ))
            
            for reagent in step.reagents:
                reagent_uuid = str(uuid.uuid4())
                reagent_data = reagent.model_dump()
                
                # Upsert compound
                c_info = upsert_compound(conn, reagent, route_uuid)
                
                cursor.execute("""
                INSERT INTO step_reagents (
                    uuid, step_uuid, route_uuid, compound_uuid, name, role, smiles, selfies, mw, 
                    pkg_size, pkg_price, cost_per_g, moles, mass, mass_unit, is_limiting, raw_reagent_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    reagent_uuid, step_uuid, route_uuid, c_info["uuid"], reagent.name, reagent.role, 
                    reagent.smiles, reagent.selfies, reagent.mw, reagent.pkg_size, reagent.pkg_price, 
                    reagent.cost_per_g, reagent.moles, reagent.mass, reagent.mass_unit, 
                    1 if reagent.is_limiting else 0, json.dumps(reagent_data)
                ))

    # 4. Save Analysis Run (always)
    analysis_uuid = str(uuid.uuid4())
    results_json = request.analysis_results.model_dump()
    cursor.execute("""
    INSERT INTO analysis_runs (
        uuid, route_uuid, target_mass_kg, total_cost, cost_per_kg, e_factor, 
        overall_yield_percent, created_at, raw_results_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        analysis_uuid, route_uuid, request.target_mass_kg, request.analysis_results.total_cost, 
        request.analysis_results.cost_per_kg, request.analysis_results.e_factor, 
        request.analysis_results.overall_yield_percent, now, json.dumps(results_json)
    ))
    
    return {
        "route_uuid": route_uuid,
        "route_hash": route_hash,
        "analysis_run_uuid": analysis_uuid
    }

def validate_route_without_saving(request: Any) -> dict:
    """Dry-run the save operation to see compound assignments."""
    conn = connect_db()
    cursor = conn.cursor()
    
    new_count = 0
    updated_count = 0
    ambiguous_compounds = []
    compound_assignments = []
    
    seen_compounds = set()
    
    for step in request.route.steps:
        for reagent in step.reagents:
            # We use name+smiles+selfies as key for uniqueness in the dry run
            key = f"{reagent.name}|{reagent.smiles or ''}|{reagent.selfies or ''}"
            if key in seen_compounds:
                continue
            seen_compounds.add(key)
            
            props = canonicalize_smiles(reagent.smiles)
            can_smiles = props["canonical_smiles"]
            inchikey = props["inchikey"]
            
            compound_data = {
                "name": reagent.name,
                "smiles": reagent.smiles,
                "canonical_smiles": can_smiles,
                "selfies": reagent.selfies,
                "inchikey": inchikey
            }
            
            uuid_found, basis, confidence = find_existing_compound(conn, compound_data)
            ambiguous = is_ambiguous(reagent.name, can_smiles, reagent.selfies, inchikey)
            
            status = "updated" if uuid_found else "new"
            if status == "new": new_count += 1
            else: updated_count += 1
            
            if ambiguous:
                ambiguous_compounds.append(reagent.name)
                
            compound_assignments.append({
                "name": reagent.name,
                "compound_uuid": uuid_found or "pending",
                "status": status,
                "dedupe_basis": basis or "none",
                "dedupe_confidence": confidence
            })
            
    conn.close()
    return {
        "new_compounds": new_count,
        "updated_compounds": updated_count,
        "ambiguous_compounds": list(set(ambiguous_compounds)),
        "compound_assignments": compound_assignments
    }
