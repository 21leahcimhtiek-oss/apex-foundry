# Monetization

Apex Foundry uses an **open-core** model: the agent runtime is open source
(Apache-2.0), while managed deployment, scale, and enterprise controls are paid.

## Pricing tiers

| Tier       | Price/mo | What's included |
|------------|----------|-----------------|
| **Free**   | $0       | 1 commander, 2 specialists, community tools, 10 req/day |
| **Pro**    | $29      | 5 commanders, unlimited specialists, all tools, 5k req/day |
| **Enterprise** | $299 | Unlimited agents, SSO/SAML, Vault secrets, SLA |

## What's gated per tier

- **Agent counts** (commanders/specialists) — enforced at blueprint registration.
- **Request rate** — daily request quota per API key.
- **Tool catalog** — community tools on Free; full built-in catalog on Pro+.
- **Enterprise controls** — SSO/SAML, Vault-backed secrets, SLA support.

## Upgrade funnel

1. Developer discovers the OSS repo, self-hosts the Free tier.
2. Free-tier limits (10 req/day, 3 agents) create natural upgrade pressure.
3. `GET /billing/plans` surfaces tiers in-product; `POST /billing/checkout/{plan}`
   opens a Stripe Checkout session (subscription, monthly).
4. Successful payment → `checkout.session.completed` webhook → entitlement
   update (provisioning of tier limits is the next integration point).
5. Enterprise is sales-assisted: checkout can still be used with a custom
   invoice/annual price, or contact link.

## Stripe setup

1. Install the optional extra: `pip install apex-foundry[billing]`.
2. Configure env vars (never commit them; use `.env`/secret store):
   - `STRIPE_API_KEY` — secret key (`sk_live_...` / `sk_test_...`).
   - `STRIPE_WEBHOOK_SECRET` — webhook signing secret (`whsec_...`).
   - Optional: `STRIPE_SUCCESS_URL`, `STRIPE_CANCEL_URL`.
3. Point a Stripe webhook endpoint at `POST /billing/webhook`, subscribing to
   `checkout.session.completed`, `invoice.paid`, `customer.subscription.deleted`.
4. Without `STRIPE_API_KEY`, the catalog is read-only and checkout returns
   **503** — local dev and CI need zero external services. The webhook
   endpoint accepts unverified JSON payloads only when
   `STRIPE_WEBHOOK_SECRET` is unset (dev/CI); with the secret set, signatures
   are verified and bad signatures get **400**.
