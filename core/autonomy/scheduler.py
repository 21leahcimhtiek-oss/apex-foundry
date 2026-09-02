"""Autonomy maintenance scheduler — the self-running half of the stack.

A background asyncio loop that periodically runs the retention pass
(prune stale autonomy records) for every registered tenant. Interval and
retention window come from env (free/local defaults); failures are logged,
never raised — hygiene must not take the API down.
"""

from __future__ import annotations

import asyncio
import logging
import os

from core.autonomy.engine import AutonomyEngine

log = logging.getLogger("apex.autonomy")

DEFAULT_INTERVAL_HOURS = 1.0
DEFAULT_MAX_AGE_HOURS = 24 * 30.0
DEFAULT_KEEP_RECENT = 10


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


class MaintenanceScheduler:
    def __init__(
        self,
        engine: AutonomyEngine,
        tenant_ids: list[str],
        interval_hours: float | None = None,
        max_age_hours: float | None = None,
        keep_recent: int | None = None,
    ) -> None:
        self.engine = engine
        self.tenant_ids = tenant_ids
        self.interval_hours = interval_hours or max(
            _env_float("APEX_AUTONOMY_PRUNE_INTERVAL_HOURS", DEFAULT_INTERVAL_HOURS),
            1 / 60,  # floor: 1 minute
        )
        self.max_age_hours = max_age_hours or _env_float(
            "APEX_AUTONOMY_MAX_AGE_HOURS", DEFAULT_MAX_AGE_HOURS
        )
        self.keep_recent = (
            keep_recent
            if keep_recent is not None
            else int(_env_float("APEX_AUTONOMY_KEEP_RECENT", DEFAULT_KEEP_RECENT))
        )
        self.last_report: list[dict] = []

    def run_once(self) -> list[dict]:
        """One prune pass across all tenants. Returns a per-tenant report."""
        report: list[dict] = []
        for tenant_id in self.tenant_ids:
            try:
                deleted, kept = self.engine.prune(
                    tenant_id, "free", self.max_age_hours, self.keep_recent
                )
                report.append({"tenant_id": tenant_id, "pruned": len(deleted), "kept": kept})
            except Exception as exc:  # noqa: BLE001 — hygiene must never crash the loop
                log.warning("autonomy prune failed for %s: %s", tenant_id, exc)
                report.append({"tenant_id": tenant_id, "error": str(exc)})
        self.last_report = report
        if any(r.get("pruned") for r in report):
            log.info("autonomy maintenance: %s", report)
        return report

    async def run_forever(self, stop: asyncio.Event) -> None:
        interval = self.interval_hours * 3600
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                self.run_once()