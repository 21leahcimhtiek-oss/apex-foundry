"""Billing router — Stripe Checkout + plan-sync webhook.

Checkout requires STRIPE_API_KEY (loaded from .env); without it the
catalog is read-only (503) so dev/CI work with zero external services.
When STRIPE_PRO_PRICE_ID / STRIPE_ENTERPRISE_PRICE_ID exist, real Stripe
Prices are used; otherwise inline price_data is sent.
"""

from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from api.routers.auth import get_current_user, get_service
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


PRICE_ID_VARS = {"pro": "STRIPE_PRO_PRICE_ID", "enterprise": "STRIPE_ENTERPRISE_PRICE_ID"}


@router.post("/checkout/{plan_id}")
def checkout(plan_id: str, user: dict = Depends(get_current_user)) -> dict:
    plan = PLANS.get(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"Unknown plan: {plan_id}")
    if plan_id == "free":
        # Free needs no payment session; downgrade/keep is instant.
        get_service().set_plan(user["tenant_id"], "free")
        return {"plan": "free", "status": "active"}
    if not os.getenv("STRIPE_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Billing not configured: set STRIPE_API_KEY to enable checkout",
        )
    body = _create_checkout_session(plan_id, plan, user)
    return {"plan": plan_id, "status": "checkout_session_created", **body}


def _create_checkout_session(plan_id: str, plan: Plan, user: dict) -> dict:
    """Create a real Stripe Checkout Session (lazy stripe import).

    Uses pre-created Stripe Prices when STRIPE_<PLAN>_PRICE_ID is set;
    falls back to inline price_data. The tenant identity rides in
    metadata so the webhook can upgrade the right tenant.
    """
    try:
        import stripe  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=503,
            detail="stripe package not installed: pip install apex-foundry[billing]",
        ) from exc

    stripe.api_key = os.environ["STRIPE_API_KEY"]
    price_var = PRICE_ID_VARS.get(plan_id)
    if price_var and os.getenv(price_var):
        line_items: list[dict] = [
            {"quantity": 1, "price": os.environ[price_var]},
        ]
    else:
        line_items = [
            {
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": plan.price_monthly * 100,
                    "recurring": {"interval": "month"},
                    "product_data": {"name": f"Apex Foundry {plan.name}"},
                },
            }
        ]
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=line_items,
            success_url=os.getenv(
                "STRIPE_SUCCESS_URL",
                "https://apex-foundry.dev/billing/success?session_id={CHECKOUT_SESSION_ID}",
            ),
            cancel_url=os.getenv(
                "STRIPE_CANCEL_URL", "https://apex-foundry.dev/billing/cancel"
            ),
            client_reference_id=user["tenant_id"],
            metadata={"plan_id": plan_id, "tenant_id": user["tenant_id"]},
        )
    except Exception as exc:  # stripe.APIError etc.
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/verify/{session_id}")
def verify(session_id: str, user: dict = Depends(get_current_user)) -> dict:
    """Webhook-free plan activation.

    Polls Stripe for the checkout session's status; if paid/completed and
    the session belongs to this tenant, the plan is applied immediately.
    Call this from the success page after payment.
    """
    if not os.getenv("STRIPE_API_KEY"):
        raise HTTPException(status_code=503, detail="Billing not configured")
    import stripe

    stripe.api_key = os.environ["STRIPE_API_KEY"]
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc}") from exc

    # StripeObject blocks .get()/iteration — use to_dict() when available.
    to_dict = getattr(session, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
    else:
        data = {
            field: getattr(session, field, None)
            for field in ("status", "payment_status", "client_reference_id", "metadata")
        }
    metadata = data.get("metadata") or {}
    tenant_id = metadata.get("tenant_id") or data.get("client_reference_id")
    if tenant_id != user["tenant_id"]:
        raise HTTPException(status_code=403, detail="Session belongs to another tenant")

    paid = data.get("payment_status") == "paid" or (
        data.get("status") == "complete" and data.get("payment_status") != "unpaid"
    )
    if not paid:
        return {
            "session_id": session_id,
            "status": data.get("payment_status", "unknown"),
            "applied": False,
        }

    plan_id = metadata.get("plan_id", "pro")
    tenant = get_service().set_plan(user["tenant_id"], plan_id)
    return {
        "session_id": session_id,
        "status": "paid",
        "applied": True,
        "plan": tenant["plan"],
    }


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

    event_type = event.get("type") if isinstance(event, dict) else event["type"]
    applied: dict | None = None
    if event_type == "checkout.session.completed":
        data = event.get("data", {}).get("object", {})
        metadata = data.get("metadata", {})
        tenant_id = metadata.get("tenant_id") or data.get("client_reference_id")
        plan_id = metadata.get("plan_id")
        if tenant_id and plan_id:
            try:
                get_service().set_plan(tenant_id, plan_id)
                applied = {"tenant_id": tenant_id, "plan": plan_id}
            except KeyError:
                applied = {"error": "tenant not found", "tenant_id": tenant_id}
    return {"received": True, "event_type": event_type, "applied": applied}
