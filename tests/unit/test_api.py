from fastapi.testclient import TestClient
import pytest
import sys

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
    client = make_client()
    client.post(
        "/auth/register",
        json={"tenant_name": "T", "email": "a@b.test", "password": "supersecret1"},
    )
    tok = client.post(
        "/auth/token", data={"username": "a@b.test", "password": "supersecret1"}
    ).json()["access_token"]
    resp = client.post(
        "/chat",
        json={"message": "hi", "agent": "ghost"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 404


def test_billing_plans() -> None:
    resp = make_client().get("/billing/plans")
    assert resp.status_code == 200
    prices = {p["name"]: p["price_monthly"] for p in resp.json()}
    assert prices == {"Free": 0, "Pro": 29, "Enterprise": 299}


def _register_and_login(client: TestClient, email: str) -> str:
    client.post(
        "/auth/register",
        json={"tenant_name": "T", "email": email, "password": "supersecret1"},
    )
    return client.post(
        "/auth/token", data={"username": email, "password": "supersecret1"}
    ).json()["access_token"]


def _unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)


class _FakeStripe:
    """Minimal fake of the stripe module for tests (no SDK needed)."""

    last_kwargs: dict = {}

    class Session:
        @staticmethod
        def create(**kwargs: dict) -> object:
            _FakeStripe.last_kwargs = kwargs

            class S:
                url = "https://checkout.stripe.com/pay/cs_test_123"
                id = "cs_test_123"

            return S()

    class checkout:
        pass


_FakeStripe.checkout.Session = _FakeStripe.Session


def test_checkout_unauthenticated_401(monkeypatch: pytest.MonkeyPatch) -> None:
    _unconfigured(monkeypatch)
    assert make_client().post("/billing/checkout/pro").status_code == 401


def test_checkout_unconfigured_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _unconfigured(monkeypatch)
    client = make_client()
    tok = _register_and_login(client, "bill1@t.test")
    resp = client.post(
        "/billing/checkout/pro", headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 503


def test_checkout_unknown_plan_404(monkeypatch: pytest.MonkeyPatch) -> None:
    _unconfigured(monkeypatch)
    client = make_client()
    tok = _register_and_login(client, "bill2@t.test")
    resp = client.post(
        "/billing/checkout/nope", headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 404


def test_checkout_free_downgrades_instantly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unconfigured(monkeypatch)
    client = make_client()
    tok = _register_and_login(client, "bill3@t.test")
    headers = {"Authorization": f"Bearer {tok}"}
    client.post("/billing/webhook", json={
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"tenant_id": client.get(
            "/auth/me", headers=headers).json()["tenant_id"], "plan_id": "pro"}}},
    })
    resp = client.post("/billing/checkout/free", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    tenant = client.get("/auth/me", headers=headers).json()
    assert _tenant_plan(client, headers) == "free"


def _tenant_plan(client: TestClient, headers: dict) -> str:
    from api.routers.auth import get_service

    me = client.get("/auth/me", headers=headers).json()
    return get_service().get_tenant(me["tenant_id"])["plan"]


def test_checkout_success_with_fake_stripe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    monkeypatch.delenv("STRIPE_PRO_PRICE_ID", raising=False)
    monkeypatch.setitem(sys.modules, "stripe", _FakeStripe)
    client = make_client()
    tok = _register_and_login(client, "bill4@t.test")
    resp = client.post(
        "/billing/checkout/pro", headers={"Authorization": f"Bearer {tok}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com")
    assert body["session_id"] == "cs_test_123"
    kwargs = _FakeStripe.last_kwargs
    assert kwargs["mode"] == "subscription"
    assert kwargs["metadata"]["plan_id"] == "pro"
    assert kwargs["metadata"]["tenant_id"] == kwargs["client_reference_id"]
    assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 2900


def test_webhook_dev_mode_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    _unconfigured(monkeypatch)
    resp = make_client().post(
        "/billing/webhook", json={"type": "checkout.session.completed"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["received"] is True
    assert body["event_type"] == "checkout.session.completed"


def test_webhook_upgrades_tenant_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    _unconfigured(monkeypatch)
    client = make_client()
    tok = _register_and_login(client, "upgrade@t.test")
    headers = {"Authorization": f"Bearer {tok}"}
    tenant_id = client.get("/auth/me", headers=headers).json()["tenant_id"]
    assert _tenant_plan(client, headers) == "free"

    resp = client.post("/billing/webhook", json={
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"tenant_id": tenant_id, "plan_id": "pro"}}},
    })
    assert resp.status_code == 200
    assert resp.json()["applied"] == {"tenant_id": tenant_id, "plan": "pro"}
    assert _tenant_plan(client, headers) == "pro"


def test_webhook_invalid_json_400(monkeypatch: pytest.MonkeyPatch) -> None:
    _unconfigured(monkeypatch)
    resp = make_client().post(
        "/billing/webhook",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_webhook_bad_signature_400(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("stripe")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
    resp = make_client().post(
        "/billing/webhook",
        content=b'{"type": "x"}',
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400
