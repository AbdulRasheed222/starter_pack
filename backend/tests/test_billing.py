"""Billing against a fake Stripe. Webhook signatures are checked with Stripe's real code, signed
here with the test secret the way Stripe signs them."""

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
import stripe as stripe_sdk

from app.api import app
from app.billing import stripe_client
from app.config import get_settings
from app.models import Workspace
from tests.support import as_user, create_workspace, join

SECRET = "whsec_test"
PRICE = "price_pro_test"


class FakeStripe:
    """Records calls and returns canned objects. Subscriptions live in `subscriptions`."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.subscriptions: dict[str, dict] = {}
        self._real = stripe_sdk.StripeClient("sk_test_unused")

        def record(name, result):
            def call(params=None, *args):
                self.calls.append((name, params or {}))
                return result(params) if callable(result) else result

            return call

        self.v1 = SimpleNamespace(
            customers=SimpleNamespace(create=record("customers.create", {"id": "cus_1"})),
            checkout=SimpleNamespace(
                sessions=SimpleNamespace(
                    create=record("checkout.create", {"url": "https://checkout.test/s"})
                )
            ),
            billing_portal=SimpleNamespace(
                sessions=SimpleNamespace(
                    create=record("portal.create", {"url": "https://billing.test/p"})
                )
            ),
            subscriptions=SimpleNamespace(retrieve=lambda sid: self.subscriptions[sid]),
        )

    def construct_event(self, payload, signature, secret):
        return self._real.construct_event(payload, signature, secret)


@pytest.fixture
def fake_stripe(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "stripe_price_pro", PRICE)
    fake = FakeStripe()
    app.dependency_overrides[stripe_client] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def send_event(client, event: dict, secret: str = SECRET):
    payload = json.dumps(event)
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256)
    return client.post(
        "/billing/webhook",
        content=payload,
        headers={"stripe-signature": f"t={timestamp},v1={digest.hexdigest()}"},
    )


def subscription_event(event_id: str, subscription_id: str = "sub_1") -> dict:
    return {
        "id": event_id,
        "object": "event",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": subscription_id, "object": "subscription"}},
    }


def subscription(status: str, price: str = PRICE) -> dict:
    return {
        "id": "sub_1",
        "customer": "cus_1",
        "status": status,
        "items": {"data": [{"price": {"id": price}}]},
    }


def test_checkout_creates_a_customer_once(client, fake_stripe, session):
    workspace_id = create_workspace(client)
    path = f"/workspaces/{workspace_id}/billing/checkout"
    response = client.post(path, json={"plan": "pro"}, headers=as_user())
    assert response.json() == {"url": "https://checkout.test/s"}
    client.post(path, json={"plan": "pro"}, headers=as_user())

    names = [name for name, _ in fake_stripe.calls]
    assert names == ["customers.create", "checkout.create", "checkout.create"]
    params = fake_stripe.calls[1][1]
    assert params["line_items"] == [{"price": PRICE, "quantity": 1}]
    assert params["client_reference_id"] == workspace_id
    assert params["success_url"].endswith(f"/app/{workspace_id}/billing?checkout=success")
    assert session.get(Workspace, workspace_id).stripe_customer_id == "cus_1"


def test_only_owners_manage_billing(client, fake_stripe):
    workspace_id = create_workspace(client)
    join(client, workspace_id, "user_bob", role="admin")
    bob = as_user("user_bob")
    assert client.get(f"/workspaces/{workspace_id}/billing", headers=bob).json()["plan"] == "free"
    path = f"/workspaces/{workspace_id}/billing/checkout"
    assert client.post(path, json={"plan": "pro"}, headers=bob).status_code == 403
    portal = f"/workspaces/{workspace_id}/billing/portal"
    assert client.post(portal, headers=bob).status_code == 403


def test_unknown_plans_are_refused(client, fake_stripe):
    workspace_id = create_workspace(client)
    path = f"/workspaces/{workspace_id}/billing/checkout"
    for plan in ("free", "enterprise"):
        assert client.post(path, json={"plan": plan}, headers=as_user()).status_code == 422


def test_webhook_moves_a_workspace_between_plans(client, fake_stripe, session):
    workspace_id = create_workspace(client)
    client.post(
        f"/workspaces/{workspace_id}/billing/checkout", json={"plan": "pro"}, headers=as_user()
    )
    usage = f"/workspaces/{workspace_id}/usage"
    assert client.get(usage, headers=as_user()).json()["budget_usd"] == 5

    fake_stripe.subscriptions["sub_1"] = subscription("active")
    assert send_event(client, subscription_event("evt_1")).status_code == 200
    billing = client.get(f"/workspaces/{workspace_id}/billing", headers=as_user()).json()
    assert (billing["plan"], billing["status"]) == ("pro", "active")
    assert client.get(usage, headers=as_user()).json()["budget_usd"] == 50

    # An active subscription blocks deleting the workspace, so Stripe never bills a ghost.
    assert client.delete(f"/workspaces/{workspace_id}", headers=as_user()).status_code == 409

    fake_stripe.subscriptions["sub_1"] = subscription("canceled")
    send_event(client, subscription_event("evt_2"))
    billing = client.get(f"/workspaces/{workspace_id}/billing", headers=as_user()).json()
    assert (billing["plan"], billing["status"]) == ("free", "canceled")
    assert client.delete(f"/workspaces/{workspace_id}", headers=as_user()).status_code == 204


def test_webhook_reads_the_current_state_and_ignores_repeats(client, fake_stripe):
    workspace_id = create_workspace(client)
    client.post(
        f"/workspaces/{workspace_id}/billing/checkout", json={"plan": "pro"}, headers=as_user()
    )
    fake_stripe.subscriptions["sub_1"] = subscription("active")
    send_event(client, subscription_event("evt_1"))
    fake_stripe.subscriptions["sub_1"] = subscription("canceled")
    # Stripe retries evt_1: already handled, so the plan is not re-synced.
    send_event(client, subscription_event("evt_1"))
    assert client.get(f"/workspaces/{workspace_id}/billing", headers=as_user()).json()["plan"] == (
        "pro"
    )
    # Any new event, even an old one arriving late, copies Stripe's current state.
    send_event(client, subscription_event("evt_0"))
    assert client.get(f"/workspaces/{workspace_id}/billing", headers=as_user()).json()["plan"] == (
        "free"
    )


def test_webhook_rejects_bad_signatures(client, fake_stripe):
    assert send_event(client, subscription_event("evt_1"), secret="whsec_wrong").status_code == 400
    response = client.post("/billing/webhook", content="{}", headers={"stripe-signature": "x"})
    assert response.status_code == 400


def test_unknown_prices_and_customers_change_nothing(client, fake_stripe):
    workspace_id = create_workspace(client)
    client.post(
        f"/workspaces/{workspace_id}/billing/checkout", json={"plan": "pro"}, headers=as_user()
    )
    fake_stripe.subscriptions["sub_1"] = subscription("active", price="price_other_product")
    send_event(client, subscription_event("evt_1"))
    assert client.get(f"/workspaces/{workspace_id}/billing", headers=as_user()).json()["plan"] == (
        "free"
    )
    fake_stripe.subscriptions["sub_9"] = {**subscription("active"), "customer": "cus_other"}
    assert send_event(client, subscription_event("evt_2", "sub_9")).status_code == 200


def test_billing_off_without_keys(client):
    workspace_id = create_workspace(client)
    billing = client.get(f"/workspaces/{workspace_id}/billing", headers=as_user()).json()
    assert billing["enabled"] is False
    assert [p["available"] for p in billing["plans"]] == [True, False]
    path = f"/workspaces/{workspace_id}/billing/checkout"
    assert client.post(path, json={"plan": "pro"}, headers=as_user()).status_code == 503
    assert client.post("/billing/webhook", content="{}").status_code == 503
