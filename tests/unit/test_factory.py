from core.agents.factory.blueprint import (
    AgentBlueprint,
    AgentRegistry,
    load_blueprint,
)


def test_load_blueprint_from_yaml(tmp_path) -> None:
    p = tmp_path / "bp.yaml"
    p.write_text(
        "agent_id: t-1\nname: Tester\ntier: 2\npersona: test persona\n"
        "tools: [http_fetch]\n"
    )
    bp = load_blueprint(p)
    assert bp.agent_id == "t-1"
    assert bp.tier == 2
    assert bp.tools == ["http_fetch"]


def test_registry_register_get_list() -> None:
    reg = AgentRegistry()
    reg.register(AgentBlueprint(agent_id="a", name="A", persona="", tier=1))
    assert reg.get("A").tier == 1
    assert reg.list_agents() == [
        {"name": "A", "tier": 1, "tools": [], "tags": []}
    ]


def test_registry_missing_raises() -> None:
    import pytest

    with pytest.raises(KeyError):
        AgentRegistry().get("ghost")
