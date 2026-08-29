from core.kernel.memory.store import InMemoryStore


def test_set_get_delete() -> None:
    store = InMemoryStore()
    store.set("k", {"a": 1})
    assert store.get("k") == {"a": 1}
    assert "k" in store.keys()
    store.delete("k")
    assert store.get("k") is None


def test_get_missing_returns_none() -> None:
    store = InMemoryStore()
    assert store.get("nope") is None
