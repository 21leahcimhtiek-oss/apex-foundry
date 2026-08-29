"""Chat router — main inference entrypoint with memory persistence."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.models import ChatRequest, ChatResponse
from core.agents.factory.blueprint import registry
from core.agents.commanders.base import Commander
from core.agents.specialists.base import Specialist
from core.kernel.inference import router as inference
from core.kernel.memory.store import MemoryStore, default_store

router = APIRouter(prefix="/chat", tags=["chat"])

_memory: MemoryStore | None = None


def _store() -> MemoryStore:
    global _memory
    if _memory is None:
        _memory = default_store()
    return _memory


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    intent = req.intent or inference.extract_intent(req.message)

    if req.agent:
        try:
            bp = registry.get(req.agent)
        except KeyError:
            raise HTTPException(
                status_code=404, detail=f"Unknown agent: {req.agent}"
            ) from None
        agent = Commander(bp, memory=_store()) if bp.tier == 1 else Specialist(bp)
        reply = agent.run(req.message)
    else:
        reply = inference.complete(req.message, intent_type=intent)

    _store().set("chat:last", {"message": req.message, "reply": reply})
    return ChatResponse(reply=reply, intent=intent, model=inference.select_model(intent))
