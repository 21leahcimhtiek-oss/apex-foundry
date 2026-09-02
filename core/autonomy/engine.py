"""Autonomy engine — self-running agent cycles on the durable Memory Vault.

Each cycle: recall relevant memories for a goal → record the outcome as a
durable MemoryRecord → (optionally) prune stale records. Free/local: SQLite
vault + substring recall, no external services. The retention pass is the
"oblivion" half of the stack: stale autonomy records age out so the vault
stays useful instead of growing forever.
"""

from __future__ import annotations

import secrets
import time

from core.kernel.memory.store import SQLiteStore
from core.kernel.memory.vault import MemoryVault, MemoryRecord

AUTONOMY_TAG = "autonomy"


class AutonomyEngine:
    def __init__(
        self,
        vault: MemoryVault,
        metrics_store: SQLiteStore | None = None,
    ) -> None:
        self._vault = vault
        self._metrics = metrics_store

    # -- metrics bookkeeping -------------------------------------------------
    def _bump(self, tenant_id: str, key: str, n: int = 1) -> None:
        if self._metrics is None:
            return
        k = f"autonomy:{tenant_id}:{key}"
        self._metrics.set(k, int(self._metrics.get(k) or 0) + n)

    def _count(self, tenant_id: str, key: str) -> int:
        if self._metrics is None:
            return 0
        return int(self._metrics.get(f"autonomy:{tenant_id}:{key}") or 0)

    # -- core operations ------------------------------------------------------
    def record(
        self, tenant_id: str, plan: str, agent: str, goal: str, outcome: str
    ) -> MemoryRecord:
        content = f"[{agent}] goal: {goal}" + (f" → {outcome}" if outcome else "")
        keywords = [w.lower() for w in goal.split() if len(w) > 2][:3]
        tags = [AUTONOMY_TAG, f"agent:{agent}", f"cycle:{secrets.token_hex(4)}"]
        tags += [f"goal:{w}" for w in keywords]
        record = self._vault.create(tenant_id, content, tags, plan)
        self._bump(tenant_id, "records")
        self._bump(tenant_id, f"agent:{agent}")
        return record

    def recall(
        self, tenant_id: str, goal: str, limit: int = 5, agent: str | None = None
    ) -> list[MemoryRecord]:
        keywords = [w for w in goal.lower().split() if len(w) > 2][:5]
        hits: dict[str, MemoryRecord] = {}
        for word in keywords:
            for rec in self._vault.search(
                tenant_id, query=word, tag=f"agent:{agent}" if agent else None, limit=limit
            ):
                hits[rec.memory_id] = rec
        result = sorted(hits.values(), key=lambda r: -r.created_at)[:limit]
        self._bump(tenant_id, "recall_queries")
        self._bump(tenant_id, "recall_hits", len(result))
        return result

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
        self._bump(tenant_id, "pruned", len(deleted))
        self._bump(tenant_id, "prune_runs")
        kept = len(records) - len(deleted)
        return deleted, kept

    def cycle(
        self,
        tenant_id: str,
        plan: str,
        agent: str,
        goal: str,
        outcome: str,
        recall_agent_scoped: bool = True,
    ) -> tuple[list[MemoryRecord], MemoryRecord]:
        """One autonomy tick: recall past memory, then record the outcome.

        With recall_agent_scoped (default), the agent only recalls its own
        history; set False to recall across all agents in the tenant."""
        recalled = self.recall(
            tenant_id, goal, agent=agent if recall_agent_scoped else None
        )
        recorded = self.record(tenant_id, plan, agent, goal, outcome)
        return recalled, recorded

    def metrics(self, tenant_id: str) -> dict:
        records = self._vault.search(tenant_id, tag=AUTONOMY_TAG, limit=200)
        by_agent: dict[str, int] = {}
        for rec in records:
            for t in rec.tags:
                if t.startswith("agent:"):
                    by_agent[t[len("agent:"):]] = by_agent.get(t[len("agent:"):], 0) + 1
        queries = self._count(tenant_id, "recall_queries")
        hits = self._count(tenant_id, "recall_hits")
        last_age = int(time.time() - records[0].created_at) if records else None
        return {
            "total_records": self._count(tenant_id, "records") or len(records),
            "records_in_vault": len(records),
            "prune_runs": self._count(tenant_id, "prune_runs"),
            "records_pruned": self._count(tenant_id, "pruned"),
            "recall_queries": queries,
            "recall_hit_rate": round(hits / queries, 3) if queries else None,
            "by_agent": by_agent,
            "seconds_since_last_record": last_age,
        }