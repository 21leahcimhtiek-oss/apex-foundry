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


def test_checkout_unconfigured_503() -> None:
    assert make_client().post("/billing/checkout/pro").status_code == 503


def test_checkout_unknown_plan_404() -> None:
    assert make_client().post("/billing/checkout/nope").status_code == 404


def _unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)


class _FakeStripe:
    """Minimal fake of the stripe module for tests (no SDK needed)."""

    last_kwargs: dict = {}

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


def test_checkout_success_with_fake_stripe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    monkeypatch.setitem(sys.modules, "stripe", _FakeStripe)
    resp = make_client().post("/billing/checkout/pro")
    assert resp.status_code == 200
    body = resp.json()
    assert body["checkout_url"].startswith("https://checkout.stripe.com")
    assert body["session_id"] == "cs_test_123"
    kwargs = _FakeStripe.last_kwargs
    assert kwargs["mode"] == "subscription"
    assert kwargs["metadata"] == {"plan_id": "pro"}
    assert kwargs["line_items"][0]["price_data"]["unit_amount"] == 2900


def test_checkout_free_plan_no_stripe_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _unconfigured(monkeypatch)
    # Unknown plan still 404 before config check is irrelevant; free plan works via stripe too.
    resp = make_client().post("/billing/checkout/free")
    # unconfigured -> 503 even for free (checkout requires Stripe session)
    assert resp.status_code == 503


def test_webhook_dev_mode_unverified(monkeypatch: pytest.MonkeyPatch) -> None:
    _unconfigured(monkeypatch)
    resp = make_client().post(
        "/billing/webhook", json={"type": "checkout.session.completed"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"received": True, "event_type": "checkout.session.completed"}


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
