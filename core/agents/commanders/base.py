"""Commander agents — tier 1, orchestrate specialists toward a goal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.agents.specialists.base import Specialist
from core.kernel.inference import router as inference
from core.kernel.memory.store import MemoryStore
from core.tools.registry import ToolRegistry, registry as default_tools

if TYPE_CHECKING:
    from core.agents.factory.blueprint import AgentBlueprint


class Commander:
    def __init__(
        self,
        blueprint: "AgentBlueprint",
        specialists: list[Specialist] | None = None,
        tools: ToolRegistry | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self.bp = blueprint
        self.specialists = specialists or []
        self.tools = tools or default_tools
        self.memory = memory

    def plan(self, goal: str) -> list[str]:
        """Ask the model for a short numbered plan, returned as steps."""
        system = self.bp.persona or f"You are {self.bp.name}, a commander agent."
        raw = inference.complete(
            f"Break this goal into at most 5 numbered steps. Reply with the "
            f"steps only.\n\nGoal: {goal}",
            intent_type="research",
            system=system,
        )
        return [
            line.lstrip(" 0123456789.-) ")
            for line in raw.splitlines()
            if line.strip()
        ]

    def delegate(self, step: str) -> list[str]:
        """Send one step to every specialist; collect their outputs."""
        return [s.run(step) for s in self.specialists]

    def execute(self, goal: str) -> dict:
        """Plan → delegate → summarize. Persists the outcome if memory set."""
        steps = self.plan(goal)
        results: list[str] = []
        for step in steps:
            results.extend(self.delegate(step))
        summary = inference.complete(
            f"Goal: {goal}\n\nStep results:\n" + "\n".join(results[:10]),
            intent_type="simple",
            system=f"Summarize the outcome for commander {self.bp.name}.",
        )
        if self.memory is not None:
            self.memory.set(f"mission:{goal[:64]}", {"steps": steps, "summary": summary})
        return {"goal": goal, "steps": steps, "results": results, "summary": summary}

    def run_tool(self, tool_name: str, **kwargs: object) -> object:
        return self.tools.get(tool_name).run(**kwargs)
