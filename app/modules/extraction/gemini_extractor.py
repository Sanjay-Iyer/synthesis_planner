"""
Gemini-backed route extractor.

Parses free-text experimental procedures into structured route drafts via the
unified ``google-genai`` SDK. The same code runs on any machine — it picks the
auth backend from the environment:

* **API key** (e.g. a personal laptop): ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY``.
* **Vertex AI via gcloud** (e.g. a locked-down work laptop): set
  ``GOOGLE_GENAI_USE_VERTEXAI=true`` + ``GOOGLE_CLOUD_PROJECT`` and authenticate
  with Application Default Credentials (``gcloud auth application-default
  login``) — no API key in the environment.

Designed for the free tier (10 RPM) with a simple rate limiter. The extractor
conforms to the ``RouteExtractor`` protocol defined in ``service.py`` — swap it
in via ``get_extractor()``.
"""
import json
import time
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter — 10 requests / 60 seconds for the Gemini free tier
# ---------------------------------------------------------------------------

class RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(self, max_calls: int = 10, period_seconds: float = 60.0):
        self._max = max_calls
        self._period = period_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def wait(self):
        """Block until a request slot is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                # Evict timestamps older than the window
                self._timestamps = [
                    t for t in self._timestamps if now - t < self._period
                ]
                if len(self._timestamps) < self._max:
                    self._timestamps.append(now)
                    return
                # Calculate wait time until the oldest timestamp expires
                wait_seconds = self._period - (now - self._timestamps[0])

            logger.info("Rate limit reached — waiting %.1fs", wait_seconds)
            time.sleep(max(wait_seconds + 0.1, 0.5))


_rate_limiter = RateLimiter(max_calls=10, period_seconds=60.0)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a chemistry lab-notebook parser. Given a free-text experimental
procedure, extract every piece of structured data you can find.

Return ONLY a JSON object (no markdown fences, no commentary) with this
exact schema:

{
  "steps": [
    {
      "step_id": <int, sequential starting at 1>,
      "name": <string or null — a short title for the step>,
      "product_mw": <float or null — molecular weight of the product>,
      "reagents": [
        {
          "name": <string — chemical name>,
          "mw": <float or null>,
          "equivalents": <float or null>,
          "mass": <float or null>,
          "mass_unit": <"g"|"mg"|"kg" or null>,
          "is_limiting": <bool — true for the limiting reagent>,
          "smiles": <string or null>,
          "selfies": <string or null>,
          "cost_per_g": <float or null>,
          "pkg_size": <float or null>,
          "pkg_price": <float or null>,
          "needs_review": [<list of field names that are missing/uncertain>]
        }
      ],
      "yield_percent": <float or null>,
      "temperature": <string or null, e.g. "80C", "RT", "reflux">,
      "time": <string or null, e.g. "4 h", "overnight">,
      "procedure": <string — the original text chunk for this step>,
      "depends_on": [<list of step_id ints this step feeds from>],
      "solvent_name": <string or null>,
      "solvent_volume": <float or null>,
      "solvent_volume_unit": <string or null, e.g. "mL", "L">,
      "needs_review": [<list of step-level field names that are missing/uncertain>]
    }
  ],
  "target_molecule": <string or null>,
  "warnings": [<list of warning strings>]
}

Rules:
- Solvents go in solvent_name/solvent_volume, NOT in the reagents list.
- The limiting reagent (usually the one defining the stoichiometry, equiv=1.0)
  should have is_limiting=true. Only ONE per step.
- If a value is stated in the text, extract it. If it is NOT stated, set it
  to null and add the field name to needs_review.
- "equivalents" is a molar ratio (the limiting reagent = 1.0), NOT absolute
  moles.
- Mass must be converted to the stated unit (g, mg, or kg). Do not convert.
- For multi-step procedures, set depends_on to the step_id(s) that feed into
  each subsequent step.
- Do NOT invent data. Only extract what the text explicitly states.
"""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

class GeminiRouteExtractor:
    """
    Gemini extractor behind the ``RouteExtractor`` protocol.

    Lazily initializes the SDK client on first call so the import cost is only
    paid when actually used (and so the app boots fine without credentials if
    the mock extractor is selected).
    """

    def __init__(self, model_name: Optional[str] = None):
        self._client = None
        self.auth_mode = None
        # Explicit selection (validated against the catalog) wins; otherwise
        # the env default is resolved lazily in _init_model().
        self.model_name = model_name

    def _init_model(self):
        """One-time SDK client initialization.

        Chooses the auth backend from the environment so the same code runs
        unchanged on any machine (see the module docstring).
        """
        if self._client is not None:
            return

        import os
        from dotenv import load_dotenv

        load_dotenv()  # reads .env in the project root

        from .service import _env_truthy
        from google import genai

        if _env_truthy(os.getenv("GOOGLE_GENAI_USE_VERTEXAI")):
            # Vertex AI — credentials come from gcloud Application Default
            # Credentials; no API key is read from the environment.
            project = os.getenv("GOOGLE_CLOUD_PROJECT")
            if not project:
                raise RuntimeError(
                    "Vertex AI mode is on (GOOGLE_GENAI_USE_VERTEXAI=true) but "
                    "GOOGLE_CLOUD_PROJECT is not set. Set it and run "
                    "`gcloud auth application-default login`."
                )
            location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
            self._client = genai.Client(
                vertexai=True, project=project, location=location
            )
            self.auth_mode = "vertex"
        else:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
            if not api_key or api_key == "your-api-key-here":
                raise RuntimeError(
                    "No Gemini credentials found. Set GEMINI_API_KEY in .env, or "
                    "enable Vertex AI with GOOGLE_GENAI_USE_VERTEXAI=true + "
                    "GOOGLE_CLOUD_PROJECT."
                )
            self._client = genai.Client(api_key=api_key)
            self.auth_mode = "api_key"

        if not self.model_name:
            self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        logger.info(
            "Gemini client initialized (model=%s, auth=%s)",
            self.model_name, self.auth_mode,
        )

    # -- public interface (matches RouteExtractor protocol) -----------------

    def parse(self, text: str, target_molecule: Optional[str] = None) -> dict:
        """Parse free-text procedure into a route draft via Gemini."""
        from .service import EXTRACTOR_VERSION as _unused, REQUIRED_REAGENT_FIELDS

        self._init_model()

        if not text or not text.strip():
            return _empty_response(target_molecule, self.model_name)

        user_prompt = text.strip()
        if target_molecule:
            user_prompt += f"\n\n[Target molecule: {target_molecule}]"

        # ---------- call Gemini (rate-limited) ----------
        _rate_limiter.wait()

        try:
            from google.genai import types
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.1,   # low temp for deterministic extraction
                ),
            )
            raw = (response.text or "").strip()
        except Exception as exc:
            logger.error("Gemini API call failed: %s", exc)
            return _error_response(str(exc), text, target_molecule)

        # ---------- parse the JSON response ----------
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try stripping markdown fences in case the model wraps it
            cleaned = raw
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            try:
                data = json.loads(cleaned.strip())
            except json.JSONDecodeError as exc2:
                logger.error("Gemini returned unparseable JSON: %s", raw[:500])
                return _error_response(
                    f"Model returned invalid JSON: {exc2}", text, target_molecule
                )

        # ---------- normalise into our schema ----------
        return _normalise(data, target_molecule, REQUIRED_REAGENT_FIELDS, self.model_name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(data: dict, target_molecule: Optional[str], required_fields: list, model_name: str) -> dict:
    """Ensure the Gemini output conforms to our ParseResponse shape.

    Defensive against a model that emits ``null`` for list fields or omits the
    required ``step_id`` — either would otherwise raise (iterating ``None``) or
    fail response validation and surface as a 500 to the user.
    """
    # `or []` (not a default) so an explicit null collapses to an empty list.
    raw_steps = data.get("steps") or []
    if not isinstance(raw_steps, list):
        raw_steps = []
    warnings = data.get("warnings") or []
    if not isinstance(warnings, list):
        warnings = []

    missing_total = 0
    steps = []
    for idx, step in enumerate(raw_steps, start=1):
        if not isinstance(step, dict):
            continue
        # step_id is required downstream; backfill from position if missing/bad.
        if not isinstance(step.get("step_id"), int):
            step["step_id"] = idx

        # Ensure needs_review exists at step level
        step.setdefault("needs_review", [])
        for field in ("name", "product_mw", "yield_percent"):
            if step.get(field) is None and field not in step["needs_review"]:
                step["needs_review"].append(field)

        # Ensure each reagent has needs_review (guard against a null list).
        reagents = step.get("reagents") or []
        if not isinstance(reagents, list):
            reagents = []
        reagents = [r for r in reagents if isinstance(r, dict)]
        for reagent in reagents:
            reagent["is_limiting"] = bool(reagent.get("is_limiting"))
            reagent.setdefault("needs_review", [])
            for field in required_fields:
                if reagent.get(field) is None and field not in reagent["needs_review"]:
                    reagent["needs_review"].append(field)
            missing_total += len(reagent["needs_review"])
        step["reagents"] = reagents

        missing_total += len(step["needs_review"])

        # Ensure defaults
        step.setdefault("depends_on", [])
        step.setdefault("procedure", "")
        steps.append(step)

    return {
        "steps": steps,
        "target_molecule": data.get("target_molecule") or target_molecule,
        "warnings": warnings,
        "extractor": model_name,
        "missing_required_count": missing_total,
    }


def _empty_response(target_molecule: Optional[str], model_name: str) -> dict:
    return {
        "steps": [{
            "step_id": 1, "name": None, "product_mw": None,
            "reagents": [{"name": "", "mw": None, "equivalents": None,
                          "mass": None, "mass_unit": "g", "is_limiting": False,
                          "smiles": None, "selfies": None, "cost_per_g": None,
                          "pkg_size": None, "pkg_price": None,
                          "needs_review": ["name", "mw", "equivalents", "mass"]}],
            "yield_percent": None, "temperature": None, "time": None,
            "procedure": "", "depends_on": [],
            "solvent_name": None, "solvent_volume": None,
            "solvent_volume_unit": None,
            "needs_review": ["name", "product_mw", "yield_percent"],
        }],
        "target_molecule": target_molecule,
        "warnings": ["No text provided — created one empty step to fill in manually."],
        "extractor": model_name,
        "missing_required_count": 7,
    }


def _error_response(error: str, text: str, target_molecule: Optional[str]) -> dict:
    """Fall back to the mock extractor on Gemini failure."""
    from .service import extract_route_draft
    result = extract_route_draft(text, target_molecule)
    result["warnings"].insert(0, f"Gemini failed ({error}) — used heuristic fallback.")
    result["extractor"] = "heuristic-fallback (gemini error)"
    return result
