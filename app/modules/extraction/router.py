"""
Experiment Setup router — parse free-text procedures into a partial route draft.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile

from .schemas import ParseRequest, ParseResponse, ModelsResponse
from . import service

# Guard against giant uploads filling memory; procedures are small.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

router = APIRouter(prefix="/api/experiment", tags=["experiment"])


@router.get("/models", response_model=ModelsResponse)
def list_models():
    """Return the editable catalog of selectable Gemini models for the dropdown.

    Sourced from ``data/gemini_models.json`` — edit that file to add/remove
    models without touching code.
    """
    return {"models": service.load_gemini_models()}


@router.get("/status")
def extractor_status():
    """Report the live extraction backend (auth mode) for the UI indicator."""
    return service.extractor_status()


@router.post("/parse", response_model=ParseResponse)
def parse_procedure(request: ParseRequest):
    """
    Convert a free-text experimental procedure into a partial synthesis-route
    draft. Missing/uncertain fields are left empty and listed per-item in
    `needs_review` so the Planner can highlight what still needs input.
    """
    extractor = service.get_extractor(model_id=request.model)
    return extractor.parse(request.text, target_molecule=request.target_molecule)


@router.post("/extract-file")
async def extract_file(file: UploadFile = File(...)):
    """Extract plain text from an uploaded .txt or .docx file.

    Lets users load a procedure from a document instead of copy-pasting it;
    the returned text is dropped into the textarea for review before parsing.
    """
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5 MB).")
    try:
        text = service.extract_document_text(file.filename, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not text:
        raise HTTPException(
            status_code=422, detail="No readable text found in the file."
        )
    return {"text": text, "filename": file.filename}
