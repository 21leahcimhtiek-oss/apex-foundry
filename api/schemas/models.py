"""Pydantic schemas for the Apex Foundry API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=32_000)
    agent: str | None = None
    intent: str | None = None


class ChatResponse(BaseModel):
    reply: str
    intent: str
    model: str


class AgentInfo(BaseModel):
    name: str
    tier: int
    tools: list[str] = []
    tags: list[str] = []


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=64_000)
    tags: list[str] = []


class MemoryRecord(BaseModel):
    memory_id: str
    tenant_id: str
    content: str
    tags: list[str]
    created_at: int


class AutonomyTickRequest(BaseModel):
    agent: str = Field(min_length=1, max_length=128)
    goal: str = Field(min_length=1, max_length=2_000)
    outcome: str = Field(default="", max_length=32_000)
    recall_agent_scoped: bool = True


class AutonomyTickResponse(BaseModel):
    recalled: list[MemoryRecord]
    recorded: MemoryRecord


class AutonomyPruneRequest(BaseModel):
    max_age_hours: float = Field(default=24 * 30, gt=0, le=24 * 365)
    keep_recent: int = Field(default=10, ge=0, le=200)


class AutonomyPruneResponse(BaseModel):
    deleted: list[str]
    kept: int


class AutonomyMetricsResponse(BaseModel):
    total_records: int
    records_in_vault: int
    prune_runs: int
    records_pruned: int
    recall_queries: int
    recall_hit_rate: float | None
    by_agent: dict[str, int]
    seconds_since_last_record: int | None


class Plan(BaseModel):
    name: str
    price_monthly: int
    features: list[str]
