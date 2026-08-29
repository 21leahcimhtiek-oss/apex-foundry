"""Apex Foundry API — FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from api.routers import agents, billing, chat, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="Apex Foundry",
        description="Greenfield agentic platform (Path B)",
        version="0.1.0",
    )
    app.include_router(health.router)
    app.include_router(agents.router)
    app.include_router(chat.router)
    app.include_router(billing.router)
    return app


app = create_app()
