from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime

class CompoundInput(BaseModel):
    name: str
    smiles: Optional[str] = None
    selfies: Optional[str] = None
    mw: Optional[float] = None
    notes: Optional[str] = None

class CompoundRecord(BaseModel):
    uuid: str
    name: str
    normalized_name: Optional[str] = None
    smiles: Optional[str] = None
    canonical_smiles: Optional[str] = None
    selfies: Optional[str] = None
    inchikey: Optional[str] = None
    formula: Optional[str] = None
    mw: Optional[float] = None
    exact_mw: Optional[float] = None
    cas: Optional[str] = None
    compound_type: Optional[str] = None
    is_defined_structure: int = 1
    dedupe_basis: Optional[str] = None
    dedupe_confidence: Optional[str] = None
    first_seen: str
    last_seen: str
    notes: Optional[str] = None
    seen_in_routes: Optional[List[str]] = []

class RouteReagentInput(BaseModel):
    name: str
    mw: float
    pkg_size: float = 1.0
    pkg_price: float = 0.0
    cost_per_g: float = 0.0
    moles: float
    mass: float
    mass_unit: str = "g"
    is_limiting: bool = False
    smiles: Optional[str] = None
    selfies: Optional[str] = None
    role: Optional[str] = None

class RouteStepInput(BaseModel):
    step_id: int
    name: str
    product_mw: float = 0.0
    reagents: List[RouteReagentInput]
    molarity: float = 0.5
    solvent_name: Optional[str] = "Solvent"
    solvent_volume: float = 0.0
    solvent_volume_unit: str = "mL"
    solvent_volume_l: float = 0.0
    solvent_density: float = 0.85
    solvent_bottle_l: float = 1.0
    solvent_bottle_price: float = 0.0
    solvent_price_per_l: float = 0.0
    yield_percent: float = 100.0
    procedure: Optional[str] = ""
    temperature: Optional[str] = "RT"
    time: Optional[str] = "N/A"
    depends_on: List[int] = []

class RouteInput(BaseModel):
    steps: List[RouteStepInput]

class AnalysisResultsInput(BaseModel):
    total_cost: float
    cost_per_kg: float
    e_factor: float
    overall_yield_percent: Optional[float] = None

class SaveRouteRequest(BaseModel):
    route_label: str
    target_molecule: Optional[str] = "Unknown Target"
    target_mass_kg: float = 1.0
    source_file: Optional[str] = None
    route: RouteInput
    analysis_results: AnalysisResultsInput

class CompoundAssignment(BaseModel):
    name: str
    compound_uuid: str
    status: str  # "new", "updated", "ambiguous"
    dedupe_basis: str # "canonical_smiles", "inchikey", "selfies", "normalized_name", "none"
    dedupe_confidence: str # "high", "medium", "low"

class SaveRouteResponse(BaseModel):
    success: bool
    route_uuid: str
    route_hash: str
    analysis_run_uuid: str
    new_compounds: int
    updated_compounds: int
    ambiguous_compounds: List[str]
    compound_assignments: List[CompoundAssignment]

class ValidateRouteResponse(BaseModel):
    new_compounds: int
    updated_compounds: int
    ambiguous_compounds: List[str]
    compound_assignments: List[CompoundAssignment]

class DatabaseSummaryResponse(BaseModel):
    compound_count: int
    route_count: int
    analysis_run_count: int
    ambiguous_compound_count: int
    most_recent_routes: List[Any]
    most_reused_compounds: List[Any]
