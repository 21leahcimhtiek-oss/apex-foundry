"""Memory kernel — pluggable storage with Redis and in-process backends.

The platform talks to the `MemoryStore` protocol only, so backends are
swappable per deployment tier (in-memory dev → Redis prod → Chroma semantic).
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol


class MemoryStore(Protocol):
    def get(self, key: str) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...
    def keys(self) -> list[str]: ...


class InMemoryStore:
    """Dev/test backend. Not persistent."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def keys(self) -> list[str]:
        return sorted(self._data)


class RedisStore:
    """Production short-term memory backend (lazy redis import/connect)."""

    def __init__(self, url: str | None = None, prefix: str = "apex:") -> None:
        import redis  # lazy — keeps dev installs light

        self._client = redis.Redis.from_url(
            url or os.getenv("REDIS_URL", "redis://localhost:6379")
        )
        self._prefix = prefix

    def _k(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Any:
        raw = self._client.get(self._k(key))
        return json.loads(raw) if raw is not None else None

    def set(self, key: str, value: Any) -> None:
        self._client.set(self._k(key), json.dumps(value, default=str))

    def delete(self, key: str) -> None:
        self._client.delete(self._k(key))

    def keys(self) -> list[str]:
        return sorted(
            k.decode().removeprefix(self._prefix)
            for k in self._client.keys(f"{self._prefix}*")
        )


def default_store() -> MemoryStore:
    """Pick a backend from REDIS_URL; fall back to in-memory if unreachable."""
    url = os.getenv("REDIS_URL")
    if url:
        try:
            store = RedisStore(url)
            store._client.ping()  # noqa: SLF001 — connectivity check
            return store
        except Exception:  # noqa: BLE001 — graceful dev fallback
            pass
    return InMemoryStore()
