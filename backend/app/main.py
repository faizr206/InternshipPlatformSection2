"""Coop Platform: one integrated app for P01-P07 (BUS2010 Internship Practicum Platform).

Each module owns its router under app/modules/. The React frontend is built into
frontend/dist and served here, so the whole platform runs from one process.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.modules.applications.router import router as applications_router
from app.modules.matching.router import router as matching_router
from app.modules.profiles.router import router as profiles_router

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Coop Platform (P01-P07)", lifespan=lifespan)

app.include_router(profiles_router)
app.include_router(applications_router)
app.include_router(matching_router)


@app.get("/api/health", include_in_schema=False)
def health():
    return {"status": "ok"}


if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    """Serve the single-page app; unknown non-API paths fall back to index.html for client routing."""
    if path.startswith("api/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    candidate = FRONTEND_DIST / path
    if path and candidate.is_file() and FRONTEND_DIST in candidate.resolve().parents:
        return FileResponse(candidate)
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse({"detail": "Frontend not built yet. Run `npm run build` in frontend/, "
                                   "or use the Vite dev server. API docs: /docs"}, status_code=503)
