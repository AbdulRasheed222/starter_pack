"""Billing with Stripe: plans, Checkout, the customer portal, and a webhook that keeps each
workspace's plan in step with its subscription.

Stripe is the source of truth. The webhook doesn't trust the order or content of events: for
any subscription event it fetches the subscription from Stripe and copies its current state.
Retried deliveries are skipped by event id. Owners manage billing; everyone else sees the plan.

To add a plan: add it to `plans()`, create its price in Stripe, and put the price id in config.
"""

import uuid
from dataclasses import dataclass, replace
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal, get_session
from app.models import StripeEvent, Workspace
from app.tenancy import Member, Owner

router = APIRouter(tags=["billing"])

SessionDep = Annotated[Session, Depends(get_session)]

# Subscription statuses that keep the paid plan. past_due keeps it while Stripe retries the
# card; Stripe moves it on to canceled or unpaid if the retries fail.
PAID_STATUSES = {"active", "trialing", "past_due"}


@dataclass(frozen=True)
class Plan:
    key: str
    paid: bool
    price_id: str | None  # the Stripe price; a paid plan without one can't be bought yet
    # [module:ai]
    ai_monthly_budget_usd: float = 0.0
    # [/module:ai]


def plans(settings: Settings) -> dict[str, Plan]:
    free = Plan("free", paid=False, price_id=None)
    pro = Plan("pro", paid=True, price_id=settings.stripe_price_pro)
    # [module:ai]
    free = replace(free, ai_monthly_budget_usd=settings.ai_monthly_budget_usd)
    pro = replace(pro, ai_monthly_budget_usd=settings.pro_ai_monthly_budget_usd)
    # [/module:ai]
    return {"free": free, "pro": pro}


def plan_for_price(settings: Settings, price_id: str | None) -> str:
    for plan in plans(settings).values():
        if plan.paid and price_id is not None and plan.price_id == price_id:
            return plan.key
    return "free"


# [module:ai]
def plan_budget(workspace: Workspace, settings: Settings) -> float:
    plan = plans(settings).get(workspace.plan) or plans(settings)["free"]
    return plan.ai_monthly_budget_usd


# [/module:ai]


def stripe_client():
    """A dependency, so tests can replace Stripe with app.dependency_overrides."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=503, detail="Billing is not set up.")
    import stripe

    return stripe.StripeClient(settings.stripe_secret_key)


StripeDep = Annotated[Any, Depends(stripe_client)]


class PlanOut(BaseModel):
    key: str
    available: bool
    # [module:ai]
    ai_monthly_budget_usd: float
    # [/module:ai]


class BillingOut(BaseModel):
    enabled: bool
    plan: str
    status: str | None
    can_manage: bool
    plans: list[PlanOut]


class CheckoutIn(BaseModel):
    plan: str


class RedirectOut(BaseModel):
    url: str


@router.get("/workspaces/{workspace_id}/billing", response_model=BillingOut)
def billing(membership: Member, session: SessionDep) -> BillingOut:
    settings = get_settings()
    workspace = session.get(Workspace, membership.workspace_id)
    assert workspace is not None
    enabled = bool(settings.stripe_secret_key)
    return BillingOut(
        enabled=enabled,
        plan=workspace.plan,
        status=workspace.subscription_status,
        can_manage=membership.role == "owner",
        plans=[
            PlanOut(
                key=p.key,
                available=not p.paid or (enabled and p.price_id is not None),
                # [module:ai]
                ai_monthly_budget_usd=p.ai_monthly_budget_usd,
                # [/module:ai]
            )
            for p in plans(settings).values()
        ],
    )


def _billing_url(workspace_id: uuid.UUID, settings: Settings, result: str = "") -> str:
    url = f"{settings.site_url.rstrip('/')}/app/{workspace_id}/billing"
    return f"{url}?checkout={result}" if result else url


@router.post("/workspaces/{workspace_id}/billing/checkout", response_model=RedirectOut)
def checkout(
    body: CheckoutIn, membership: Owner, session: SessionDep, stripe: StripeDep
) -> RedirectOut:
    settings = get_settings()
    plan = plans(settings).get(body.plan)
    if plan is None or not plan.paid:
        raise HTTPException(status_code=422, detail="Unknown plan.")
    if plan.price_id is None:
        raise HTTPException(status_code=503, detail="This plan has no Stripe price set up.")
    workspace = session.get(Workspace, membership.workspace_id)
    assert workspace is not None
    if workspace.subscription_status in PAID_STATUSES:
        raise HTTPException(
            status_code=409, detail="This workspace already has a subscription. Manage it instead."
        )
    if workspace.stripe_customer_id is None:
        customer = stripe.v1.customers.create(
            params={"name": workspace.name, "metadata": {"workspace_id": str(workspace.id)}}
        )
        workspace.stripe_customer_id = customer["id"]
        session.commit()
    result = stripe.v1.checkout.sessions.create(
        params={
            "mode": "subscription",
            "customer": workspace.stripe_customer_id,
            "client_reference_id": str(workspace.id),
            "line_items": [{"price": plan.price_id, "quantity": 1}],
            "subscription_data": {"metadata": {"workspace_id": str(workspace.id)}},
            "success_url": _billing_url(workspace.id, settings, "success"),
            "cancel_url": _billing_url(workspace.id, settings, "cancelled"),
        }
    )
    return RedirectOut(url=result["url"])


@router.post("/workspaces/{workspace_id}/billing/portal", response_model=RedirectOut)
def portal(membership: Owner, session: SessionDep, stripe: StripeDep) -> RedirectOut:
    """Stripe's own page for changing the card, the plan, or cancelling."""
    workspace = session.get(Workspace, membership.workspace_id)
    assert workspace is not None
    if workspace.stripe_customer_id is None:
        raise HTTPException(status_code=409, detail="This workspace has no billing account yet.")
    result = stripe.v1.billing_portal.sessions.create(
        params={
            "customer": workspace.stripe_customer_id,
            "return_url": _billing_url(workspace.id, get_settings()),
        }
    )
    return RedirectOut(url=result["url"])


def sync_subscription(session: Session, stripe, subscription_id: str, settings: Settings) -> None:
    """Copy a subscription's current state from Stripe onto its workspace."""
    subscription = stripe.v1.subscriptions.retrieve(subscription_id)
    workspace = session.scalar(
        select(Workspace).where(Workspace.stripe_customer_id == subscription["customer"])
    )
    if workspace is None:
        # A customer this app didn't create, e.g. from another product on the same account.
        return
    status = subscription["status"]
    items = subscription["items"]["data"]
    price_id = items[0]["price"]["id"] if items else None
    workspace.subscription_status = status
    workspace.stripe_subscription_id = subscription["id"]
    workspace.plan = plan_for_price(settings, price_id) if status in PAID_STATUSES else "free"


def handle_event(stripe, payload: bytes, signature: str | None, settings: Settings) -> None:
    try:
        event = stripe.construct_event(payload, signature, settings.stripe_webhook_secret)
    except Exception as exc:  # bad signature or malformed payload
        raise HTTPException(status_code=400, detail="Invalid signature.") from exc

    with SessionLocal() as session:
        session.add(StripeEvent(id=event["id"], type=event["type"]))
        try:
            session.flush()
        except IntegrityError:
            return  # a retried delivery of an event already handled
        data = event["data"]["object"]
        if event["type"] == "checkout.session.completed" and data.get("subscription"):
            sync_subscription(session, stripe, data["subscription"], settings)
        elif event["type"].startswith("customer.subscription."):
            sync_subscription(session, stripe, data["id"], settings)
        session.commit()


@router.post("/billing/webhook")
async def webhook(request: Request, stripe: StripeDep) -> dict[str, bool]:
    """Called by Stripe, not by users: it is authenticated by Stripe's signature."""
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=503, detail="Billing is not set up.")
    # The signature covers the exact bytes, so read them before anything parses the body.
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    await run_in_threadpool(handle_event, stripe, payload, signature, settings)
    return {"received": True}
