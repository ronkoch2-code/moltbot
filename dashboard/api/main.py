"""FastAPI dashboard application for heartbeat activity monitoring."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dashboard.api.database import init_db
from dashboard.api.models import HealthOut
from dashboard.api.routers import actions, runs, stats

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


@app.get("/api/health", response_model=HealthOut)
def health_check():
    """Health check endpoint."""
    return HealthOut(status="ok", database="ok")


# Serve React static files — must be last so it doesn't shadow API routes
STATIC_DIR = Path(__file__).resolve().parent.parent / "webapp" / "dist"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


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
