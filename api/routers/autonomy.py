"""Autonomy router — agent cycles backed by the Memory Vault (/v1/autonomy).

tick: recall relevant memories for a goal, record the outcome durably.
prune: retention pass — age out stale autonomy records (operator/plan-safe).
Both endpoints are metered against the tenant's plan allowance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.routers.auth import get_current_user, get_service
from api.routers.memory import get_vault
from api.schemas.models import (
    AutonomyMetricsResponse,
    AutonomyPruneRequest,
    AutonomyPruneResponse,
    AutonomyTickRequest,
    AutonomyTickResponse,
)
from core.autonomy.engine import AutonomyEngine
from core.kernel.memory.store import SQLiteStore

router = APIRouter(prefix="/v1/autonomy", tags=["autonomy"])

_engine: AutonomyEngine | None = None


def get_engine() -> AutonomyEngine:
    global _engine
    if _engine is None:
        _engine = AutonomyEngine(get_vault(), SQLiteStore())
    return _engine


def _metered(user: dict) -> None:
    try:
        get_service().check_and_increment_usage(user["tenant_id"])
    except PermissionError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=429, detail=str(exc)) from None


def _plan(user: dict) -> str:
    return get_service().get_tenant(user["tenant_id"])["plan"]


@router.post("/tick", response_model=AutonomyTickResponse)
def autonomy_tick(
    req: AutonomyTickRequest, user: dict = Depends(get_current_user)
) -> AutonomyTickResponse:
    _metered(user)
    recalled, recorded = get_engine().cycle(
        user["tenant_id"],
        _plan(user),
        req.agent,
        req.goal,
        req.outcome,
        recall_agent_scoped=req.recall_agent_scoped,
    )
    return AutonomyTickResponse(recalled=recalled, recorded=recorded)


@router.post("/prune", response_model=AutonomyPruneResponse)
def autonomy_prune(
    req: AutonomyPruneRequest, user: dict = Depends(get_current_user)
) -> AutonomyPruneResponse:
    _metered(user)
    deleted, kept = get_engine().prune(
        user["tenant_id"], _plan(user), req.max_age_hours, req.keep_recent
    )
    return AutonomyPruneResponse(deleted=deleted, kept=kept)


@router.get("/metrics", response_model=AutonomyMetricsResponse)
def autonomy_metrics(user: dict = Depends(get_current_user)) -> AutonomyMetricsResponse:
    return AutonomyMetricsResponse(**get_engine().metrics(user["tenant_id"]))