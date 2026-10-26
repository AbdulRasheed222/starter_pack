# Billing

Workspaces subscribe through [Stripe](https://stripe.com). There are two plans out of the box: **free** and **pro**. Owners upgrade with Stripe Checkout and manage cards, invoices and cancelling in the Stripe customer portal. Everyone else in the workspace sees the plan but can't change it.

The code is in [`billing.py`](../backend/src/app/billing.py) and [`Billing.tsx`](../web/components/Billing.tsx).

## How the plan stays right

Stripe is the source of truth. The webhook at `POST /billing/webhook`:

1. checks Stripe's signature over the exact request body, and refuses anything else with a 400;
2. records the event id, and skips the event if it was handled before (Stripe retries deliveries);
3. for `checkout.session.completed` and every `customer.subscription.*` event, fetches the subscription from Stripe and copies its current status and price onto the workspace.

Because step 3 reads the current state instead of trusting the event, events that arrive late or out of order can't leave a workspace on the wrong plan. If the fetch fails, nothing is saved and Stripe's retry handles it.

A workspace is on its paid plan while the subscription is `active`, `trialing` or `past_due` (Stripe is retrying the card). Any other status puts it on free. A workspace with a paid subscription can't be deleted until the subscription is cancelled, so nobody is billed for a workspace that no longer exists.

## Set it up

1. In the Stripe dashboard, in **test mode**, create a product with a recurring price. Copy the price id (`price_…`).
2. Save the customer portal settings once (Settings, Billing, Customer portal). Stripe won't open the portal until you do.
3. Set the API's environment:

| Variable | Value |
| --- | --- |
| `STRIPE_SECRET_KEY` | `sk_test_…` from Developers, API keys |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…`, from the step below |
| `STRIPE_PRICE_PRO` | the price id |
| `PRO_AI_MONTHLY_BUDGET_USD` | the pro plan's AI budget per month; free uses `AI_MONTHLY_BUDGET_USD` | <!-- [only:ai] -->

With `STRIPE_SECRET_KEY` empty, billing is off: everyone stays on free and the billing page says so.

### Try it

Forward Stripe's events to your machine with the [Stripe CLI](https://docs.stripe.com/stripe-cli):

```sh
stripe login
stripe listen --forward-to localhost:8000/billing/webhook   # prints the whsec_… to use
```

Open a workspace's billing page as its owner, upgrade, and pay with the test card `4242 4242 4242 4242`, any future date and any CVC. The page should show **Pro** within a few seconds. Then open **Manage billing**, cancel, and check the plan returns to free when the subscription ends.

### In production

Repeat the steps in live mode. Add an endpoint in Developers, Webhooks pointing to `https://your-api/billing/webhook`, listening to `checkout.session.completed` and `customer.subscription.created`, `.updated` and `.deleted`. Use its signing secret as `STRIPE_WEBHOOK_SECRET`.

## Adding a plan

1. Add it to `plans()` in `billing.py`, with a setting for its price id in `config.py`.
2. Create the price in Stripe and set the setting.
3. Add its name to `billing.plan.<key>` in every file under `web/messages/`.

Limits that depend on the plan read `workspace.plan`. Read it on the server, never from the browser.
