"""FastAPI dashboard application for heartbeat activity monitoring."""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dashboard.api.database import init_db
from dashboard.api.models import HealthOut
from dashboard.api.routers import actions, prompts, runs, security, stats

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=getattr(logging, os.environ.get("LOG_LEVEL", "INFO")),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

_DB_INIT_MAX_RETRIES = 5
_DB_INIT_BACKOFF_BASE = 2  # seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup with retry.

    PostgreSQL may still be starting when the dashboard launches.
    Retry with exponential backoff so the dashboard survives this.
    """
    for attempt in range(1, _DB_INIT_MAX_RETRIES + 1):
        try:
            init_db()
            logger.info("Dashboard API started (db init on attempt %d)", attempt)
            break
        except psycopg2.OperationalError as exc:
            if attempt < _DB_INIT_MAX_RETRIES:
                wait = _DB_INIT_BACKOFF_BASE ** attempt
                logger.warning(
                    "Database connection failed on init (attempt %d/%d), retrying in %ds: %s",
                    attempt, _DB_INIT_MAX_RETRIES, wait, exc,
                )
                time.sleep(wait)
            else:
                raise
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
app.include_router(security.router)


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
