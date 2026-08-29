from fastapi.testclient import TestClient

from api.main import create_app
from core.agents.factory.blueprint import AgentBlueprint, registry


def make_client() -> TestClient:
    registry.register(
        AgentBlueprint(agent_id="t", name="Testy", persona="p", tier=2)
    )
    return TestClient(create_app())


def test_health() -> None:
    resp = make_client().get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_list_agents() -> None:
    resp = make_client().get("/agents")
    assert resp.status_code == 200
    assert any(a["name"] == "Testy" for a in resp.json())


def test_get_agent_404() -> None:
    assert make_client().get("/agents/ghost").status_code == 404


def test_chat_unknown_agent_404() -> None:
    resp = make_client().post("/chat", json={"message": "hi", "agent": "ghost"})
    assert resp.status_code == 404


def test_billing_plans() -> None:
    resp = make_client().get("/billing/plans")
    assert resp.status_code == 200
    prices = {p["name"]: p["price_monthly"] for p in resp.json()}
    assert prices == {"Free": 0, "Pro": 29, "Enterprise": 299}


def test_checkout_unconfigured_503() -> None:
    assert make_client().post("/billing/checkout/pro").status_code == 503


def test_checkout_unknown_plan_404() -> None:
    assert make_client().post("/billing/checkout/nope").status_code == 404
