# Monetization — Apex Foundry

Open-core SaaS. Core (this repo) is Apache-2.0; paid tiers add hosted
operation, scale, and enterprise controls.

## Pricing (mirrored in `api/routers/billing.py` → `GET /billing/plans`)

| Tier       | Price     | Includes                                        |
|------------|-----------|-------------------------------------------------|
| Free       | $0        | 1 commander, 2 specialists, community tools, 10 req/day |
| Pro        | $29/mo    | 5 commanders, unlimited specialists, all tools, 5k req/day |
| Enterprise | $299/mo   | unlimited agents, SSO/SAML, Vault secrets, SLA  |

## Revenue streams

1. **SaaS subscriptions** — primary. Managed hosting of the platform per
   the tiers above (Stripe Checkout; billing router is already wired and
   returns 503 until `STRIPE_API_KEY` is set).
2. **Open-core enterprise license** — SSO/SAML, audit log, and Vault
   integration live in a private `enterprise/` overlay repo, never in
   this Apache-2.0 codebase.
3. **Blueprint marketplace** — rev-share on community-authored agent
   blueprints (70/30).
4. **Metered inference** — pass-through model cost + 20% above tier
   request allowances.

## Go-to-market checklist

- [x] Plan catalog implemented (`/billing/plans`)
- [x] Checkout endpoint stubbed with feature-flag (503 without key)
- [x] Auth + multi-tenancy in API (JWT, tenants, roles, per-tenant metering)
- [ ] Stripe account + products/prices created (Free/Pro/Enterprise)
- [ ] `STRIPE_API_KEY` set in prod env → checkout goes live
- [ ] Webhook handler for `checkout.session.completed` (gate usage limits)
- [ ] Plan changes wired into tenant records (upgrade/downgrade flow)
- [ ] Landing page + terms/privacy pages
- [ ] Launch: Show HN + r/LocalLLaMA + X build-in-public thread

## Sequencing rule

Free tier can launch once the Stripe webhook gates plan limits. Paid
checkout can be enabled immediately after the Stripe account exists —
the auth/multi-tenancy prerequisite is satisfied.
