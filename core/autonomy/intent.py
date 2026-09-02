"""Intent Router — central dispatch from intents to registered agent handlers.

An intent arrives as {intent, payload, agent}. The router routes to the
handler registered for that intent (falling back to the wildcard handler),
records the dispatch and its result as durable autonomy records (the event
stream: tag `event:<status>`), and returns the outcome. Handlers are plain
callables — thin wrappers around real capabilities (prune, tick, health).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from core.autonomy.engine import AUTONOMY_TAG, AutonomyEngine

EVENT_TAG = "event"


class UnknownIntentError(LookupError):
    pass


class IntentRouter:
    def __init__(self, engine: AutonomyEngine) -> None:
        self.engine = engine
        self._handlers: dict[str, Callable[[dict], Any]] = {}

    def register(self, intent: str, handler: Callable[[dict], Any]) -> None:
        """Bind an intent to a handler callable(payload) -> result."""
        self._handlers[intent] = handler

    @property
    def intents(self) -> list[str]:
        return sorted(self._handlers)

    def dispatch(
        self,
        tenant_id: str,
        plan: str,
        agent: str,
        intent: str,
        payload: dict | None = None,
    ) -> dict:
        """Route one intent to its handler; persist the outcome as an event.

        Handlers are called as handler(payload, ctx) where ctx carries the
        tenant context — handlers never see or need the raw credentials."""
        handler = self._handlers.get(intent)
        started = int(time.time())
        ctx = {"tenant_id": tenant_id, "plan": plan}
        if handler is None:
            status, result = "error", {"detail": f"unknown intent: {intent}"}
        else:
            try:
                status, result = "ok", handler(payload or {}, ctx)
            except Exception as exc:  # noqa: BLE001 — errors become events, not crashes
                status, result = "error", {"detail": str(exc)}
        record = self.engine.record(
            tenant_id,
            plan,
            agent,
            f"dispatch {intent} [{status}]",
            str(result)[:1000],
        )
        # Tag as event for stream reads (record() already wrote the record;
        # append the event tags via the vault's tag search surface).
        self._tag_event(record.memory_id, tenant_id, status)
        return {
            "intent": intent,
            "status": status,
            "result": result,
            "event_id": record.memory_id,
            "dispatched_at": started,
        }

    def _tag_event(self, memory_id: str, tenant_id: str, status: str) -> None:
        conn = self.engine._vault._conn  # noqa: SLF001 — same-process vault
        row = conn.execute(
            "SELECT tags FROM memories WHERE memory_id = ? AND tenant_id = ?",
            (memory_id, tenant_id),
        ).fetchone()
        if row is None:
            return
        import json

        tags = json.loads(row[0]) + [EVENT_TAG, f"event:{status}"]
        conn.execute(
            "UPDATE memories SET tags = ? WHERE memory_id = ?",
            (json.dumps(tags), memory_id),
        )
        conn.commit()

    def events(self, tenant_id: str, status: str | None = None, limit: int = 50) -> list:
        """Read the event stream, newest first, optionally filtered by status."""
        records = self.engine._vault.search(
            tenant_id, tag=EVENT_TAG, limit=min(limit, 200)
        )
        if status:
            records = [r for r in records if f"event:{status}" in r.tags]
        return records

    # -- built-in capability bindings ----------------------------------------
    def install_defaults(self) -> None:
        """Bind the platform's own capabilities as routable intents."""
        self.register("memory.prune", lambda p, ctx: self.engine.prune(
            ctx["tenant_id"], ctx.get("plan", "free"),
            p.get("max_age_hours", 24 * 30), p.get("keep_recent", 10),
        ))
        self.register("memory.recall", lambda p, ctx: [
            r.model_dump() for r in self.engine.recall(
                ctx["tenant_id"], p.get("goal", ""),
                limit=p.get("limit", 5), agent=p.get("agent"),
            )
        ])
        self.register("system.status", lambda p, ctx: {
            "intents": self.intents,
            "engine": "ready",
        })