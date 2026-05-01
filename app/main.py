"""
Synthesis Architect — Main Application Entry Point.

Mounts all module routers and serves the frontend static files.
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.modules.synthesis.router import router as synthesis_router
from app.modules.risk.router import router as risk_router

# =================================================================
# APP SETUP
# =================================================================

app = FastAPI(title="Synthesis Architect", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================================================================
# MODULE ROUTERS
# =================================================================

app.include_router(synthesis_router)
app.include_router(risk_router)

# =================================================================
# STATIC FILE SERVING
# =================================================================

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def root():
    """Serve the landing page."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/{page}.html")
async def serve_page(page: str):
    """Serve any HTML page by name."""
    file_path = STATIC_DIR / f"{page}.html"
    if file_path.exists():
        return FileResponse(file_path)
    return {"error": "Page not found"}


# Mount static assets (CSS, JS) — must come after route definitions
app.mount("/css", StaticFiles(directory=STATIC_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=STATIC_DIR / "js"), name="js")
