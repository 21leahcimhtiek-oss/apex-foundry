"""Specialist agents — tier 2, bind tools and one persona."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.kernel.inference import router as inference
from core.tools.registry import ToolRegistry, registry as default_tools

if TYPE_CHECKING:
    from core.agents.factory.blueprint import AgentBlueprint


class Specialist:
    def __init__(
        self,
        blueprint: "AgentBlueprint",
        tools: ToolRegistry | None = None,
    ) -> None:
        self.bp = blueprint
        self.tools = tools or default_tools

    def run(self, task: str) -> str:
        system = self.bp.persona or f"You are {self.bp.name}, a specialist agent."
        return inference.complete(
            task,
            intent_type=(
                self.bp.model_preference
                if self.bp.model_preference != "auto"
                else None
            ),
            system=system,
        )

    def run_tool(self, tool_name: str, **kwargs: object) -> object:
        return self.tools.get(tool_name).run(**kwargs)
