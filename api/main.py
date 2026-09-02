"""Apex Foundry API — FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI


def _load_env() -> None:
    """Minimal .env loader (no dependency). Does not override real env."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value)


_load_env()

from api.routers import agents, auth, billing, chat, health, memory
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
    app.include_router(memory.router)
    return app


app = create_app()


def run() -> None:  # pragma: no cover - CLI entrypoint
    """Entrypoint: `apex-foundry` (via [project.scripts])."""
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)
