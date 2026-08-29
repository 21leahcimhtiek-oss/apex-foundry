"""Billing router — plan catalog for the open-core monetization model.

Stripe integration is behind STRIPE_API_KEY; without it the catalog is
read-only so local dev and CI work with zero external services.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, HTTPException, Request

from api.schemas.models import Plan

router = APIRouter(prefix="/billing", tags=["billing"])

PLANS: dict[str, Plan] = {
    "free": Plan(
        name="Free",
        price_monthly=0,
        features=["1 commander", "2 specialists", "community tools", "10 req/day"],
    ),
    "pro": Plan(
        name="Pro",
        price_monthly=29,
        features=["5 commanders", "unlimited specialists", "all tools", "5k req/day"],
    ),
    "enterprise": Plan(
        name="Enterprise",
        price_monthly=299,
        features=["unlimited agents", "SSO/SAML", "Vault secrets", "SLA"],
    ),
}


@router.get("/plans")
def list_plans() -> list[Plan]:
    return list(PLANS.values())


@router.post("/checkout/{plan_id}")
def checkout(plan_id: str) -> dict:
    plan = PLANS.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Unknown plan: {plan_id}")
    if not os.getenv("STRIPE_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Billing not configured: set STRIPE_API_KEY to enable checkout",
        )
    return {"plan": plan_id, "status": "checkout_session_created", **_create_checkout_session(plan_id, plan)}


def _create_checkout_session(plan_id: str, plan: Plan) -> dict:
    """Create a real Stripe Checkout Session (lazy stripe import).

    Runs only when STRIPE_API_KEY is set; keeps dev/CI free of the SDK.
    """
    try:
        import stripe  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=503,
            detail="stripe package not installed: pip install apex-foundry[billing]",
        ) from exc

    stripe.api_key = os.environ["STRIPE_API_KEY"]
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": plan.price_monthly * 100,
                        "recurring": {"interval": "month"},
                        "product_data": {"name": f"Apex Foundry {plan.name}"},
                    },
                }
            ],
            success_url=os.getenv(
                "STRIPE_SUCCESS_URL", "https://apex-foundry.dev/billing/success"
            ),
            cancel_url=os.getenv(
                "STRIPE_CANCEL_URL", "https://apex-foundry.dev/billing/cancel"
            ),
            metadata={"plan_id": plan_id},
        )
    except Exception as exc:  # stripe.APIError etc.
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/webhook")
async def webhook(request: Request) -> dict:
    """Stripe webhook receiver. Verifies the signature when
    STRIPE_WEBHOOK_SECRET is set; otherwise (dev/CI) accepts the payload
    unverified so the endpoint is testable without external services.
    """
    payload = await request.body()
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if secret:
        try:
            import stripe  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=503, detail="stripe package not installed") from exc
        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig, secret)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {exc}") from exc
    else:
        try:
            event = json.loads(payload or b"{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    return {"received": True, "event_type": event.get("type") if isinstance(event, dict) else event["type"]}
