"""
Route extraction service.

Turns a free-text experimental procedure (e.g. pasted from an ELN) into a
*partial* synthesis-route draft for the Planner. Extraction is intentionally
lenient: any field it cannot determine is left ``None`` and named in the item's
``needs_review`` list, so the user can finish it manually after loading.

The production implementation will call an LLM. For now `MockRouteExtractor`
is a deterministic, dependency-free heuristic placeholder behind the
`RouteExtractor` interface, so the page + hand-off can be built and tested
without the model. Swap implementations in `get_extractor()`.

`extract_route_draft()` is a pure function returning plain dicts, so it can be
unit-tested without FastAPI/pydantic.
"""
import json
import logging
import re
from typing import Optional, Protocol

from app.cloud_auth import resolve_auth_settings
from app.config import GEMINI_MODELS_PATH

logger = logging.getLogger(__name__)

EXTRACTOR_VERSION = "mock-heuristic-v0"

# Fallback used when the catalog file is missing/unreadable, so the dropdown
# and extractor still have a sane default.
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Sentinel model id the UI sends to force the heuristic (no-LLM) extractor,
# regardless of whether credentials are configured.
NO_LLM_SENTINEL = "__none__"

# Fields the downstream analysis engine needs for every reagent. Any of these
# left empty on a drafted reagent is surfaced in `needs_review` for the UI.
REQUIRED_REAGENT_FIELDS = ["name", "mw", "equivalents", "mass"]

# Crude solvent lexicon — detected solvents go to the step's solvent fields
# rather than the reagent list.
COMMON_SOLVENTS = {
    "water", "thf", "dcm", "dichloromethane", "methanol", "meoh", "ethanol",
    "etoh", "acetone", "dmf", "dmso", "toluene", "hexane", "hexanes",
    "ethyl acetate", "etoac", "acetonitrile", "mecn", "chloroform",
    "diethyl ether", "ether", "dioxane", "acetic acid", "pyridine", "nmp",
}

_MASS_UNITS = {"mg", "g", "kg"}
_AMOUNT_RE = r"(\d+(?:\.\d+)?)\s*(mg|g|kg|mmol|mol|mL|L|µL|uL)\b"

# Filler words stripped from the edges of a captured reagent name. Procedure
# prose wraps chemical names in lead-ins ("to a stirred solution of X") and
# trailing verbs ("X was added"); we trim those to recover the bare name.
_NAME_STOPWORDS = {
    "to", "a", "an", "the", "of", "was", "were", "is", "are", "be", "been",
    "added", "add", "adding", "stirred", "stirring", "solution", "suspension",
    "mixture", "with", "in", "into", "and", "then", "by", "dropwise", "slowly",
    "at", "from", "after", "this", "it", "which", "gave", "give", "obtained",
    "treated", "treatment", "dissolved", "charged", "placed", "under", "over",
    "using", "use", "via", "portionwise", "resulting", "reaction", "cooled",
    "heated", "warmed", "subsequently", "sequentially", "containing", "for",
}


def _is_stopword(w: str) -> bool:
    return w.lower().strip(",.;:") in _NAME_STOPWORDS


# --- Document text extraction (for the "Load .txt / Word document" button) ---
# A .docx is a zip of XML; we read the text without the python-docx dependency.
_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _decode_text_bytes(data: bytes) -> str:
    """Best-effort decode of a plain-text upload."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _extract_docx_text(data: bytes) -> str:
    """Pull the readable text out of a .docx byte stream using only stdlib.

    Walks word/document.xml: each ``<w:p>`` is a paragraph (newline), and
    ``<w:t>`` runs hold the text, with ``<w:tab>``/``<w:br>`` as whitespace.
    """
    import io
    import zipfile
    from xml.etree import ElementTree as ET

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as e:
        raise ValueError("File does not look like a valid .docx Word document.") from e

    root = ET.fromstring(xml)
    paragraphs = []
    for para in root.iter(f"{_DOCX_NS}p"):
        parts = []
        for node in para.iter():
            tag = node.tag
            if tag == f"{_DOCX_NS}t" and node.text:
                parts.append(node.text)
            elif tag == f"{_DOCX_NS}tab":
                parts.append("\t")
            elif tag == f"{_DOCX_NS}br":
                parts.append("\n")
        paragraphs.append("".join(parts))
    return "\n".join(paragraphs).strip()


def extract_document_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded .txt or .docx file.

    Raises ``ValueError`` for unsupported types (e.g. legacy binary .doc).
    """
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return _extract_docx_text(data)
    if name.endswith((".txt", ".text", ".md")):
        return _decode_text_bytes(data).strip()
    if name.endswith(".doc"):
        raise ValueError(
            "Legacy .doc files aren't supported — save as .docx or .txt and retry."
        )
    raise ValueError("Unsupported file type. Upload a .txt or .docx file.")


def _clean_name(raw: str, anchor: str = "end") -> str:
    """Recover a bare reagent name from a captured window by taking the run of
    content words adjacent to the anchor:

      anchor="end"   name sits just before "(" (e.g. "...with antimony trioxide (")
                     -> take the *trailing* run -> "antimony trioxide"
      anchor="start" name sits just after "of" (e.g. "of THF at 80 C")
                     -> take the *leading* run  -> "THF"
    """
    words = [w for w in re.sub(r"\s+", " ", raw.strip(" ,.;:")).split(" ") if w]
    out = []
    if anchor == "end":
        for w in reversed(words):
            if _is_stopword(w):
                break
            out.append(w)
        out.reverse()
    else:
        for w in words:
            if _is_stopword(w):
                break
            out.append(w)
    return " ".join(out).strip(" ,.;:")


# ----------------------------------------------------------------------------
# Field-level heuristics
# ----------------------------------------------------------------------------

def _find_temperature(text: str) -> Optional[str]:
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*°?\s*C\b", text)
    if m:
        return f"{m.group(1)}C"
    if re.search(r"\breflux\b", text, re.I):
        return "reflux"
    if re.search(r"\broom temperature\b|\br\.?t\.?\b", text, re.I):
        return "RT"
    return None


def _find_time(text: str) -> Optional[str]:
    m = re.search(r"\bfor\s+(\d+(?:\.\d+)?)\s*(hours?|h|minutes?|min|days?|d)\b", text, re.I)
    if m:
        unit = m.group(2).lower()
        unit = {"hour": "h", "hours": "h", "minute": "min", "minutes": "min",
                "day": "d", "days": "d"}.get(unit, unit)
        return f"{m.group(1)} {unit}"
    if re.search(r"\bovernight\b", text, re.I):
        return "overnight"
    return None


def _find_yield(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*yield", text, re.I)
    if not m:
        m = re.search(r"yield[^\d%]{0,12}(\d+(?:\.\d+)?)\s*%", text, re.I)
    return float(m.group(1)) if m else None


def _parse_amount(content: str):
    """Return (mass_value, mass_unit) if an absolute mass is present, else (None, None)."""
    m = re.search(_AMOUNT_RE, content, re.I)
    if not m:
        return None, None
    value, unit = float(m.group(1)), m.group(2)
    if unit.lower() in _MASS_UNITS:
        return value, unit.lower()
    # mmol/mol/volume are real amounts but not a mass we can use without MW.
    return None, None


def _parse_equivalents(content: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*equiv", content, re.I)
    return float(m.group(1)) if m else None


def _build_reagent(name: str, mass, mass_unit, equivalents, is_limiting=False) -> dict:
    reagent = {
        "name": name,
        "mw": None,
        "equivalents": equivalents,
        "mass": mass,
        "mass_unit": mass_unit or "g",
        "is_limiting": is_limiting,
        "smiles": None,
        "selfies": None,
        "cost_per_g": None,
        "pkg_size": None,
        "pkg_price": None,
    }
    reagent["needs_review"] = [
        f for f in REQUIRED_REAGENT_FIELDS if not reagent.get(f)
    ]
    return reagent


# ----------------------------------------------------------------------------
# Reagent / solvent extraction
# ----------------------------------------------------------------------------

def _extract_reagents_and_solvent(chunk: str):
    """Pull reagents (with masses where stated) and a single solvent from a chunk."""
    reagents = []
    solvent = {"solvent_name": None, "solvent_volume": None, "solvent_volume_unit": None}
    seen = set()

    def consider(name: str, content: str, anchor: str = "end"):
        name = _clean_name(name.replace("\n", " "), anchor=anchor)
        key = name.lower()
        if not name or len(name) < 2 or key in seen:
            return
        seen.add(key)
        if key in COMMON_SOLVENTS:
            if solvent["solvent_name"] is None:
                solvent["solvent_name"] = name
                vm = re.search(r"(\d+(?:\.\d+)?)\s*(mL|L)\b", content, re.I)
                if vm:
                    solvent["solvent_volume"] = float(vm.group(1))
                    solvent["solvent_volume_unit"] = vm.group(2)
            return
        mass, unit = _parse_amount(content)
        reagents.append(_build_reagent(name, mass, unit, _parse_equivalents(content)))

    # A bare chemical name: up to 4 word-tokens. Bounding the window (rather
    # than allowing arbitrary spaces) keeps the capture from swallowing the
    # whole preceding clause when reagents are space- (not newline-) separated.
    name_frag = r"(?:[A-Za-z][A-Za-z0-9\-'’]*\s+){0,3}[A-Za-z][A-Za-z0-9\-'’]*"

    # Pattern A:  NAME ( ...amount... )      e.g. "aniline (5.0 g, 54 mmol, 1.1 equiv)"
    for m in re.finditer(rf"({name_frag})\s*\(([^)]*\d[^)]*)\)", chunk):
        consider(m.group(1), m.group(2), anchor="end")

    # Pattern B:  amount unit of NAME        e.g. "10 mL of THF", "2.0 g of NaH"
    for m in re.finditer(
        rf"(\d+(?:\.\d+)?\s*(?:mg|g|kg|mmol|mol|mL|L|µL|uL))\s+of\s+({name_frag})",
        chunk, re.I,
    ):
        consider(m.group(2), m.group(1), anchor="start")

    return reagents, solvent


def _split_steps(text: str):
    """Split on explicit 'Step N' / 'Procedure N' markers; otherwise one step."""
    parts = re.split(r"(?im)^\s*(?:step|procedure)\s+[0-9ivx]+[\.\):\-]?", text)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts if len(parts) > 1 else [text.strip()]


# ----------------------------------------------------------------------------
# Public extraction (pure)
# ----------------------------------------------------------------------------

def extract_route_draft(text: str, target_molecule: Optional[str] = None) -> dict:
    """
    Parse `text` into a partial route draft dict:

        {
          "steps": [ { ...step fields..., "reagents": [...], "needs_review": [...] } ],
          "target_molecule": str | None,
          "warnings": [str],
          "extractor": str,
          "missing_required_count": int,
        }

    Unknown fields are left None and named in per-item `needs_review`.
    """
    text = (text or "").strip()
    warnings = []
    if not text:
        return {
            "steps": [_empty_step(1)],
            "target_molecule": target_molecule,
            "warnings": ["No text provided — created one empty step to fill in manually."],
            "extractor": EXTRACTOR_VERSION,
            "missing_required_count": len(REQUIRED_REAGENT_FIELDS),
        }

    chunks = _split_steps(text)
    steps = []
    for i, chunk in enumerate(chunks, start=1):
        reagents, solvent = _extract_reagents_and_solvent(chunk)

        # Heuristic: first reagent with a stated mass is the presumed limiting
        # reagent (flagged for the user to confirm).
        step_review = []
        lim = next((r for r in reagents if r["mass"] is not None), None)
        if lim:
            lim["is_limiting"] = True
            if lim["equivalents"] is None:
                lim["equivalents"] = 1.0
                lim["needs_review"] = [f for f in lim["needs_review"] if f != "equivalents"]
            step_review.append("is_limiting")
        if not reagents:
            warnings.append(f"Step {i}: no reagents detected — add them in the Planner.")
            reagents = [_build_reagent("", None, None, None)]

        step = {
            "step_id": i,
            "name": None,
            "product_mw": None,
            "reagents": reagents,
            "yield_percent": _find_yield(chunk),
            "temperature": _find_temperature(chunk),
            "time": _find_time(chunk),
            "procedure": chunk,
            "depends_on": [i - 1] if i > 1 else [],
            **solvent,
        }
        step["needs_review"] = step_review + [
            f for f in ("name", "product_mw", "yield_percent")
            if step.get(f) in (None, "")
        ]
        steps.append(step)

    missing = sum(len(r["needs_review"]) for s in steps for r in s["reagents"])
    missing += sum(len(s["needs_review"]) for s in steps)

    return {
        "steps": steps,
        "target_molecule": target_molecule,
        "warnings": warnings,
        "extractor": EXTRACTOR_VERSION,
        "missing_required_count": missing,
    }


def _empty_step(step_id: int) -> dict:
    return {
        "step_id": step_id, "name": None, "product_mw": None,
        "reagents": [_build_reagent("", None, None, None)],
        "yield_percent": None, "temperature": None, "time": None,
        "procedure": "", "depends_on": [],
        "solvent_name": None, "solvent_volume": None, "solvent_volume_unit": None,
        "needs_review": ["name", "product_mw", "yield_percent"],
    }


# ----------------------------------------------------------------------------
# Extractor interface (LLM swaps in here later)
# ----------------------------------------------------------------------------

class RouteExtractor(Protocol):
    def parse(self, text: str, target_molecule: Optional[str] = None) -> dict: ...


class MockRouteExtractor:
    """Deterministic heuristic extractor — placeholder for the future LLM."""

    def parse(self, text: str, target_molecule: Optional[str] = None) -> dict:
        return extract_route_draft(text, target_molecule)


# ----------------------------------------------------------------------------
# Gemini model catalog
# ----------------------------------------------------------------------------

def load_gemini_models() -> list[dict]:
    """Return the editable list of selectable Gemini models.

    Reads ``data/gemini_models.json`` (``[{"name", "id"}, ...]``). Falls back to
    a single default entry if the file is missing or malformed, so the UI never
    ends up with an empty dropdown.
    """
    try:
        with open(GEMINI_MODELS_PATH, encoding="utf-8") as fh:
            models = json.load(fh).get("models", [])
        models = [m for m in models if m.get("id")]
        if models:
            return models
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read Gemini model catalog: %s", exc)
    return [{"name": "Gemini 2.5 Flash", "id": DEFAULT_GEMINI_MODEL}]


def resolve_model(model_id: Optional[str]) -> str:
    """Validate a requested model id against the catalog.

    Returns ``model_id`` if it is a known model, otherwise the first catalog
    entry (the default). This stops arbitrary client-supplied strings from being
    forwarded to the Gemini API.
    """
    models = load_gemini_models()
    allowed = {m["id"] for m in models}
    if model_id and model_id in allowed:
        return model_id
    return models[0]["id"]


def _gemini_auth_available() -> bool:
    """Whether usable Gemini credentials exist in the environment.

    Supports both backends so the same code runs on any machine:
      * Vertex AI / gcloud ADC: ``LLM_PROVIDER=vertexai``.
      * API key: ``LLM_PROVIDER=api-key``.
    """
    settings = resolve_auth_settings()
    return settings.uses_external_llm and settings.is_ready


def extractor_status() -> dict:
    """Report which extraction backend is currently live, for the UI indicator.

    ``auth_mode`` is ``"vertex"`` (gcloud ADC), ``"api_key"``, or ``"mock"``.
    """
    settings = resolve_auth_settings()
    return {
        "llm_available": settings.uses_external_llm and settings.is_ready,
        "auth_mode": settings.auth_mode,
        "provider": settings.provider,
        "configuration_error": settings.error,
    }


def get_extractor(model_id: Optional[str] = None) -> RouteExtractor:
    """Return the active extractor.

    * ``model_id == NO_LLM_SENTINEL`` → always the heuristic mock extractor
      (the explicit "No LLM" choice in the UI).
    * Otherwise uses Gemini when credentials are present — an API key or Vertex
      AI via gcloud Application Default Credentials (see
      ``_gemini_auth_available``) — with ``model_id`` validated against the
      catalog. Falls back to the heuristic when no credentials are configured.
    """
    if model_id == NO_LLM_SENTINEL:
        return MockRouteExtractor()

    settings = resolve_auth_settings()
    if settings.error:
        raise RuntimeError(settings.error)
    if settings.uses_external_llm and settings.is_ready:
        from .gemini_extractor import GeminiRouteExtractor
        return GeminiRouteExtractor(model_name=resolve_model(model_id))

    return MockRouteExtractor()
