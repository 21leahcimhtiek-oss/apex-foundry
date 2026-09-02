"""Memory Vault — durable, per-tenant memory records on SQLite (stdlib).

Each record is tenant-scoped; search is a case-insensitive substring match
over content + tags (free/local: no external embedding service required).
"""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

from api.schemas.models import MemoryRecord

# Per-plan record caps (mirrors the plan ladder in billing.py / MONETIZATION.md).
PLAN_RECORD_CAPS: dict[str, int] = {"free": 100, "pro": 10_000, "enterprise": 1_000_000}


class VaultError(Exception):
    """Domain error surfaced as HTTP by the router."""


class VaultFullError(VaultError):
    pass


class MemoryVault:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.getenv(
            "APEX_MEMORY_DB",
            str(Path(__file__).resolve().parents[3] / "data" / "memory_vault.db"),
        )
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                created_at INTEGER NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_tenant ON memories (tenant_id)"
        )
        self._conn.commit()

    def create(self, tenant_id: str, content: str, tags: list[str], plan: str) -> MemoryRecord:
        cap = PLAN_RECORD_CAPS.get(plan, PLAN_RECORD_CAPS["free"])
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM memories WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if count >= cap:
            raise VaultFullError(
                f"Memory Vault full for plan '{plan}' ({cap} records). Upgrade to store more."
            )
        memory_id = f"mem_{secrets.token_hex(8)}"
        created_at = int(time.time())
        self._conn.execute(
            "INSERT INTO memories (memory_id, tenant_id, content, tags, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (memory_id, tenant_id, content, _dump_tags(tags), created_at),
        )
        self._conn.commit()
        return MemoryRecord(
            memory_id=memory_id,
            tenant_id=tenant_id,
            content=content,
            tags=tags,
            created_at=created_at,
        )

    def get(self, tenant_id: str, memory_id: str) -> MemoryRecord | None:
        row = self._conn.execute(
            "SELECT memory_id, tenant_id, content, tags, created_at "
            "FROM memories WHERE memory_id = ? AND tenant_id = ?",
            (memory_id, tenant_id),
        ).fetchone()
        return _row_to_record(row) if row else None

    def search(
        self, tenant_id: str, query: str | None = None, tag: str | None = None, limit: int = 50
    ) -> list[MemoryRecord]:
        limit = max(1, min(limit, 200))
        rows = self._conn.execute(
            "SELECT memory_id, tenant_id, content, tags, created_at "
            "FROM memories WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()
        records = [_row_to_record(r) for r in rows]
        if query:
            q = query.lower()
            records = [
                r for r in records
                if q in r.content.lower() or any(q in t.lower() for t in r.tags)
            ]
        if tag:
            records = [r for r in records if tag.lower() in (t.lower() for t in r.tags)]
        return records[:limit]

    def delete(self, tenant_id: str, memory_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM memories WHERE memory_id = ? AND tenant_id = ?",
            (memory_id, tenant_id),
        )
        self._conn.commit()
        return cur.rowcount > 0


def _dump_tags(tags: list[str]) -> str:
    return json.dumps(tags)


def _row_to_record(row: tuple) -> MemoryRecord:
    memory_id, tenant_id, content, tags, created_at = row
    return MemoryRecord(
        memory_id=memory_id,
        tenant_id=tenant_id,
        content=content,
        tags=json.loads(tags),
        created_at=created_at,
    )