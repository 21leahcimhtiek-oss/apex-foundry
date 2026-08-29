"""Agents router — list registered blueprints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.agents.factory.blueprint import registry

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("")
def list_agents() -> list[dict]:
    return registry.list_agents()


@router.get("/{name}")
def get_agent(name: str) -> dict:
    try:
        bp = registry.get(name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {name}") from None
    return {"name": bp.name, "tier": bp.tier, "tools": bp.tools, "persona": bp.persona}
