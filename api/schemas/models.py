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


class Plan(BaseModel):
    name: str
    price_monthly: int
    features: list[str]
