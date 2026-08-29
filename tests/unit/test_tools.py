from core.tools.registry import Tool, ToolRegistry, registry


def test_register_and_run() -> None:
    reg = ToolRegistry()
    reg.register(Tool("echo", "echoes", lambda **kw: kw.get("x")))
    assert reg.get("echo").run(x=42) == 42
    assert reg.has("echo")
    assert not reg.has("nope")


def test_default_registry_has_http_fetch() -> None:
    assert registry.has("http_fetch")
