"""Health router — liveness, readiness, and version."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])

VERSION = "0.1.0"


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": VERSION}


@router.get("/ready")
def ready() -> dict:
    return {"status": "ready"}
