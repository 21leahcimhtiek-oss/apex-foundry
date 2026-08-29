"""Tool kernel — declarative tool registry with a typed protocol."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]

    def run(self, **kwargs: Any) -> Any:
        return self.handler(**kwargs)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]


def http_fetch(url: str) -> str:
    """Built-in: GET a URL and return the body text (trimmed)."""
    import httpx

    resp = httpx.get(url, timeout=15, follow_redirects=True)
    return json.dumps({"status": resp.status_code, "body": resp.text[:8000]})


registry = ToolRegistry()
registry.register(Tool("http_fetch", "Fetch a URL via HTTP GET", http_fetch))
