"""Memory Vault router — durable per-tenant memory records (/v1/memory).

Backed by SQLite (stdlib, free/local stack — no paid services). Requests
are metered against the tenant's Stripe-managed plan allowance, and record
counts are capped per plan (see core/kernel/memory/vault.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.routers.auth import get_current_user, get_service
from api.schemas.models import MemoryCreate, MemoryRecord
from core.kernel.memory.vault import MemoryVault, VaultFullError

router = APIRouter(prefix="/v1/memory", tags=["memory"])

_vault: MemoryVault | None = None


def get_vault() -> MemoryVault:
    global _vault
    if _vault is None:
        _vault = MemoryVault()
    return _vault


def _metered(user: dict) -> None:
    """Count one request against the tenant's plan allowance (billing)."""
    try:
        get_service().check_and_increment_usage(user["tenant_id"])
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None


def _plan(user: dict) -> str:
    return get_service().get_tenant(user["tenant_id"])["plan"]


@router.post("", response_model=MemoryRecord, status_code=201)
def create_memory(req: MemoryCreate, user: dict = Depends(get_current_user)) -> MemoryRecord:
    _metered(user)
    try:
        return get_vault().create(
            user["tenant_id"], req.content, req.tags, _plan(user)
        )
    except VaultFullError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from None


@router.get("", response_model=list[MemoryRecord])
def search_memories(
    q: str | None = Query(default=None, max_length=200),
    tag: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    user: dict = Depends(get_current_user),
) -> list[MemoryRecord]:
    _metered(user)
    return get_vault().search(user["tenant_id"], query=q, tag=tag, limit=limit)


@router.get("/{memory_id}", response_model=MemoryRecord)
def read_memory(memory_id: str, user: dict = Depends(get_current_user)) -> MemoryRecord:
    _metered(user)
    record = get_vault().get(user["tenant_id"], memory_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown memory: {memory_id}")
    return record


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, user: dict = Depends(get_current_user)) -> dict:
    _metered(user)
    if not get_vault().delete(user["tenant_id"], memory_id):
        raise HTTPException(status_code=404, detail=f"Unknown memory: {memory_id}")
    return {"deleted": True, "memory_id": memory_id}