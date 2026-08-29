"""Agent factory — declarative blueprints + runtime registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AgentBlueprint:
    agent_id: str
    name: str
    persona: str
    tier: int  # 0=Aurora 1=Commander 2=Specialist 3=Micro 4=Guardian
    model_preference: str = "auto"
    tools: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def load_blueprint(path: str | Path) -> AgentBlueprint:
    """Parse one blueprint YAML file into an AgentBlueprint."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AgentBlueprint(
        agent_id=str(raw["agent_id"]),
        name=raw["name"],
        persona=str(raw.get("persona", "")).strip(),
        tier=int(raw.get("tier", 2)),
        model_preference=raw.get("model_preference", "auto"),
        tools=list(raw.get("tools", [])),
        tags=list(raw.get("tags", [])),
    )


class AgentRegistry:
    """In-memory registry of loaded blueprints and live agent instances."""

    def __init__(self) -> None:
        self._blueprints: dict[str, AgentBlueprint] = {}

    def load_directory(self, directory: str | Path) -> int:
        count = 0
        for path in sorted(Path(directory).glob("*.yaml")):
            bp = load_blueprint(path)
            self._blueprints[bp.name] = bp
            count += 1
        return count

    def register(self, bp: AgentBlueprint) -> None:
        self._blueprints[bp.name] = bp

    def get(self, name: str) -> AgentBlueprint:
        if name not in self._blueprints:
            raise KeyError(f"Agent not registered: {name}")
        return self._blueprints[name]

    def by_tier(self, tier: int) -> list[AgentBlueprint]:
        return [b for b in self._blueprints.values() if b.tier == tier]

    def list_agents(self) -> list[dict]:
        return [
            {"name": b.name, "tier": b.tier, "tools": b.tools, "tags": b.tags}
            for b in self._blueprints.values()
        ]


registry = AgentRegistry()
