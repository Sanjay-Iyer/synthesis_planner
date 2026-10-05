"""
Pydantic I/O models for the extraction endpoint.

These are the *draft* schema: a lenient mirror of the Planner route where every
field is optional, plus per-item `needs_review` lists. This is deliberately
separate from the strict analysis schema (synthesis.engine / database.models),
which requires mw/equivalents/mass — a draft is allowed to be incomplete.
"""

from pydantic import BaseModel
from typing import List, Optional
from app.hs6 import HS6Input


class ParseRequest(BaseModel):
    text: str
    target_molecule: Optional[str] = None
    # Selected Gemini model id (validated against the catalog server-side).
    # None → use the catalog default.
    model: Optional[str] = None


class GeminiModel(BaseModel):
    name: str
    id: str


class ModelsResponse(BaseModel):
    models: List[GeminiModel] = []


class DraftReagent(BaseModel):
    name: Optional[str] = None
    hs6: HS6Input = None
    mw: Optional[float] = None
    equivalents: Optional[float] = None
    mass: Optional[float] = None
    mass_unit: Optional[str] = "g"
    is_limiting: bool = False
    smiles: Optional[str] = None
    selfies: Optional[str] = None
    cost_per_g: Optional[float] = None
    pkg_size: Optional[float] = None
    pkg_price: Optional[float] = None
    # Names of fields the extractor could not fill / is unsure about.
    needs_review: List[str] = []


class DraftStep(BaseModel):
    step_id: int
    name: Optional[str] = None
    product_mw: Optional[float] = None
    reagents: List[DraftReagent] = []
    yield_percent: Optional[float] = None
    temperature: Optional[str] = None
    time: Optional[str] = None
    procedure: Optional[str] = ""
    depends_on: List[int] = []
    solvent_name: Optional[str] = None
    solvent_volume: Optional[float] = None
    solvent_volume_unit: Optional[str] = None
    needs_review: List[str] = []


class ParseResponse(BaseModel):
    steps: List[DraftStep] = []
    target_molecule: Optional[str] = None
    warnings: List[str] = []
    extractor: str
    missing_required_count: int = 0
