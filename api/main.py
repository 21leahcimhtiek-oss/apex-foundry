"""Apex Foundry API — FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from api.routers import agents, auth, billing, chat, health
from core.agents.factory.blueprint import registry

BLUEPRINTS_DIR = Path(__file__).resolve().parent.parent / "blueprints"


def load_blueprints() -> None:
    """Load all YAML blueprints from the blueprints/ directory."""
    if BLUEPRINTS_DIR.is_dir():
        registry.load_directory(BLUEPRINTS_DIR)


def create_app() -> FastAPI:
    load_blueprints()
    app = FastAPI(
        title="Apex Foundry",
        description="Greenfield agentic platform (Path B)",
        version="0.1.0",
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(agents.router)
    app.include_router(chat.router)
    app.include_router(billing.router)
    return app


app = create_app()


def run() -> None:  # pragma: no cover - CLI entrypoint
    """Entrypoint: `apex-foundry` (via [project.scripts])."""
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
