"""Autonomy engine — self-running agent cycles on the durable Memory Vault.

Each cycle: recall relevant memories for a goal → record the outcome as a
durable MemoryRecord → (optionally) prune stale records. Free/local: SQLite
vault + substring recall, no external services. The retention pass is the
"oblivion" half of the stack: stale autonomy records age out so the vault
stays useful instead of growing forever.
"""

from __future__ import annotations

import time

from core.kernel.memory.vault import MemoryVault, MemoryRecord

AUTONOMY_TAG = "autonomy"


class AutonomyEngine:
    def __init__(self, vault: MemoryVault) -> None:
        self._vault = vault

    def record(
        self, tenant_id: str, plan: str, agent: str, goal: str, outcome: str
    ) -> MemoryRecord:
        content = f"[{agent}] goal: {goal}" + (f" → {outcome}" if outcome else "")
        return self._vault.create(
            tenant_id,
            content,
            [AUTONOMY_TAG, f"agent:{agent}"],
            plan,
        )

    def recall(self, tenant_id: str, goal: str, limit: int = 5) -> list[MemoryRecord]:
        keywords = [w for w in goal.lower().split() if len(w) > 2][:5]
        hits: dict[str, MemoryRecord] = {}
        for word in keywords:
            for rec in self._vault.search(tenant_id, query=word, limit=limit):
                hits[rec.memory_id] = rec
        return sorted(hits.values(), key=lambda r: -r.created_at)[:limit]

    def prune(
        self, tenant_id: str, plan: str, max_age_hours: float, keep_recent: int
    ) -> tuple[list[str], int]:
        """Delete autonomy records older than max_age_hours, but always keep
        the keep_recent most recent ones. Returns (deleted_ids, kept_count)."""
        cutoff = int(time.time() - max_age_hours * 3600)
        records = self._vault.search(tenant_id, tag=AUTONOMY_TAG, limit=200)
        protected = {r.memory_id for r in records[:keep_recent]}
        deleted: list[str] = []
        for rec in records:
            if rec.created_at < cutoff and rec.memory_id not in protected:
                if self._vault.delete(tenant_id, rec.memory_id):
                    deleted.append(rec.memory_id)
        kept = len(records) - len(deleted)
        return deleted, kept

    def cycle(
        self, tenant_id: str, plan: str, agent: str, goal: str, outcome: str
    ) -> tuple[list[MemoryRecord], MemoryRecord]:
        """One autonomy tick: recall past memory, then record the outcome."""
        recalled = self.recall(tenant_id, goal)
        recorded = self.record(tenant_id, plan, agent, goal, outcome)
        return recalled, recorded