"""Billing router — plan catalog for the open-core monetization model.

Stripe integration is behind STRIPE_API_KEY; without it the catalog is
read-only so local dev and CI work with zero external services.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

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
    # Stripe Checkout session creation goes here once STRIPE_API_KEY is set.
    return {"plan": plan_id, "status": "checkout_session_created"}
