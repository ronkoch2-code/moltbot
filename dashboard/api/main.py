"""FastAPI dashboard application for heartbeat activity monitoring."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard.api.database import init_db
from dashboard.api.models import HealthOut
from dashboard.api.routers import actions, prompts, runs, stats

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    init_db()
    logger.info("Dashboard API started")
    yield


app = FastAPI(
    title="Moltbot Heartbeat Dashboard",
    description="Monitor CelticXfer heartbeat activity on Moltbook",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router)
app.include_router(actions.router)
app.include_router(stats.router)
app.include_router(prompts.router)


@app.get("/api/health", response_model=HealthOut)
def health_check():
    """Health check endpoint."""
    return HealthOut(status="ok", database="ok")


# Serve React SPA — static assets + index.html fallback for client-side routing
STATIC_DIR = Path(__file__).resolve().parent.parent / "webapp" / "dist"
if STATIC_DIR.exists():
    # Mount static assets (JS/CSS bundles) at /assets
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA catch-all: serve index.html for any non-API path (React Router handles routing)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")


def main():
    """Run the dashboard server."""
    import uvicorn

    port = int(os.environ.get("DASHBOARD_PORT", "8081"))
    uvicorn.run(
        "dashboard.api.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
