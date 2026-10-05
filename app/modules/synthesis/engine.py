"""
Synthesis Engine — Stoichiometry, Cost, and Scale-up Calculations.
Migrated from python-polymer/backend/main.py
"""

from pydantic import BaseModel
from typing import List, Optional
from app.hs6 import HS6Input

# =================================================================
# DATA MODELS
# =================================================================


class ReagentInput(BaseModel):
    name: str
    hs6: HS6Input = None
    mw: float
    cost_per_g: float = 0.0
    # Molar EQUIVALENTS (a stoichiometric ratio), not an absolute mole count.
    # The limiting reagent is conventionally 1.0. See calculate_engine() for how
    # this ratio is converted to absolute moles at production scale.
    equivalents: float
    is_limiting: bool = False


class SynthesisStep(BaseModel):
    step_id: int
    name: str
    product_mw: float = 0.0
    reagents: List[ReagentInput]
    molarity: float = 0.5
    solvent_name: Optional[str] = "Solvent"
    solvent_price_per_l: float = 0.0
    solvent_density: float = 0.85
    purification_cost: float = 0.0
    yield_percent: float = 100.0
    procedure: Optional[str] = ""
    temperature: Optional[str] = "RT"
    time: Optional[str] = "N/A"
    depends_on: List[int] = []


class SynthesisProject(BaseModel):
    steps: List[SynthesisStep]
    target_mass_kg: Optional[float] = 1.0


# =================================================================
# CALCULATION ENGINE
# =================================================================


def calculate_engine(project: SynthesisProject):
    """
    Core stoichiometry engine. Given a list of synthesis steps and a
    target production mass (kg), calculates the scaled-up reagent
    masses, costs, solvent volumes, and E-factor.

    Units convention — IMPORTANT:
        Every reagent's `equivalents` field is a molar ratio, not an absolute
        mole count. The limiting reagent is conventionally 1.0 equiv.

    Two passes:
        Pass 1 establishes a per-"unit" mole flow. A unit is one batch anchored
        on 1 mole of the first step's limiting reagent. For a step with no
        upstream dependency the anchor is its own limiting reagent's equivalents
        (≈1.0); for a dependent step the anchor is the moles flowing in from the
        steps it depends on (i.e. their yielded product).

        Pass 2 multiplies the unit flow by `scale` (batches needed to hit the
        target mass) and converts each reagent's equivalents into absolute moles:
          - independent step: act_moles = equivalents * scale
                (here `scale` already equals the limiting reagent's real moles)
          - dependent step:   act_moles = equivalents * scaled_anchor
                (where `scaled_anchor` is the real moles arriving from upstream)
        Both branches treat `equivalents` consistently — they only differ in
        what "1 equivalent" is measured against, so the result is consistent.
    """
    results = []
    prod_unit, start_unit = {}, {}
    total_input_mass_g = 0
    target_kg = project.target_mass_kg or 1.0

    if not project.steps:
        return {"total_cost": 0, "cost_per_kg": 0, "e_factor": 0, "steps": []}

    sorted_steps = sorted(project.steps, key=lambda x: x.step_id)

    # Pass 1: Determine mole flow through each step
    for step in sorted_steps:
        in_mols = sum(prod_unit.get(sid, 0) for sid in step.depends_on)
        anchor = (
            in_mols
            if in_mols > 0
            else next((r.equivalents for r in step.reagents if r.is_limiting), 1.0)
        )
        start_unit[step.step_id] = anchor
        prod_unit[step.step_id] = anchor * (step.yield_percent / 100)

    # Calculate scale factor from target mass
    final_step = sorted_steps[-1]
    unit_final_g = prod_unit[final_step.step_id] * final_step.product_mw
    scale = (target_kg * 1000) / unit_final_g if unit_final_g > 0 else 1.0

    # Pass 2: Scale up and calculate costs
    total_cost = 0
    for step in sorted_steps:
        mat_cost = 0
        reagents_to_buy = []
        scaled_anchor = start_unit[step.step_id] * scale

        for r in step.reagents:
            # Dependent steps measure equivalents against the moles arriving from
            # upstream (scaled_anchor); independent steps measure against `scale`
            # (which already equals the limiting reagent's real moles). See the
            # docstring for the full rationale.
            act_moles = r.equivalents * (scaled_anchor if step.depends_on else scale)
            mass = act_moles * r.mw
            cost = mass * r.cost_per_g
            mat_cost += cost
            total_input_mass_g += mass
            reagents_to_buy.append(
                {"name": r.name, "hs6": r.hs6, "mass_g": round(mass, 2), "item_cost": round(cost, 2)}
            )

        vol = (scaled_anchor / step.molarity) if step.molarity > 0 else 0
        total_input_mass_g += vol * (step.solvent_density * 1000)
        solv_cost = vol * step.solvent_price_per_l
        total_cost += mat_cost + solv_cost + (step.purification_cost * scale)

        results.append(
            {
                "step_id": step.step_id,
                "name": step.name,
                "reagents": reagents_to_buy,
                "solvent_name": step.solvent_name,
                "solvent_l": round(vol, 3),
                "molarity": step.molarity,
                "solvent_cost": round(solv_cost, 2),
                "step_total": round(mat_cost + solv_cost, 2),
                "temperature": step.temperature,
                "time": step.time,
                "procedure": step.procedure,
            }
        )

    e_factor = (
        (total_input_mass_g - (target_kg * 1000)) / (target_kg * 1000)
        if target_kg > 0
        else 0
    )

    return {
        "steps": results,
        "total_cost": round(total_cost, 2),
        "cost_per_kg": round(total_cost / target_kg, 2),
        "e_factor": round(e_factor, 2),
    }


def audit_optimization(project: SynthesisProject):
    """
    Yield sensitivity audit. For each step, simulates what would happen
    if that step had 100% yield, and calculates the cost savings per
    1% yield improvement.
    """
    if not project.steps:
        return {"audit": [], "risk_score": 0}

    baseline = calculate_engine(project)
    audit_results = []
    total_sens = 0

    for i, step in enumerate(project.steps):
        sim = project.model_copy(deep=True)
        sim.steps[i].yield_percent = 100.0
        res = calculate_engine(sim)
        sens = (
            (baseline["cost_per_kg"] - res["cost_per_kg"]) / (100 - step.yield_percent)
            if step.yield_percent < 100
            else 0
        )
        total_sens += sens
        audit_results.append(
            {"step_id": step.step_id, "name": step.name, "sensitivity": round(sens, 2)}
        )

    return {
        "audit": audit_results,
        "risk_score": round(total_sens / len(project.steps), 2),
    }
