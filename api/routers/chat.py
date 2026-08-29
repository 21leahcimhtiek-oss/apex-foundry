"""Chat router — main inference entrypoint.

Tenant-scoped: requires a bearer token, meters usage against the plan
allowance, and persists conversation state under the tenant's namespace.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.routers.auth import get_current_user, get_service
from api.schemas.models import ChatRequest, ChatResponse
from core.agents.factory.blueprint import registry
from core.agents.commanders.base import Commander
from core.agents.specialists.base import Specialist
from core.kernel.inference import router as inference
from core.kernel.memory.store import MemoryStore, default_store

router = APIRouter(prefix="/chat", tags=["chat"])

_memory: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _memory
    if _memory is None:
        _memory = default_store()
    return _memory


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, user: dict = Depends(get_current_user)) -> ChatResponse:
    # Meter against the tenant's plan allowance.
    try:
        get_service().check_and_increment_usage(user["tenant_id"])
    except PermissionError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None

    intent = req.intent or inference.extract_intent(req.message)

    if req.agent:
        try:
            bp = registry.get(req.agent)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"Unknown agent: {req.agent}"
            ) from None
        agent = (
            Commander(bp, memory=get_store()) if bp.tier == 1 else Specialist(bp)
        )
        reply = agent.run(req.message)
    else:
        reply = inference.complete(req.message, intent_type=intent)

    get_store().set(
        f"chat:{user['tenant_id']}:last", {"message": req.message, "reply": reply}
    )
    return ChatResponse(
        reply=reply, intent=intent, model=inference.select_model(intent)
    )


@router.get("/usage")
def usage(user: dict = Depends(get_current_user)) -> dict:
    service = get_service()
    used = int(get_store().get(service.usage_key(user["tenant_id"])) or 0)
    tenant = service.get_tenant(user["tenant_id"])
    from core.auth.service import PLAN_LIMITS

    return {
        "plan": tenant["plan"],
        "used_today": used,
        "limit": PLAN_LIMITS.get(tenant["plan"], PLAN_LIMITS["free"]),
    }

