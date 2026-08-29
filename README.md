# Apex Foundry

Greenfield agentic platform (Path B of Project Chronos). Declarative,
blueprint-defined agents — commanders, specialists, guardians — on a
pluggable inference + memory kernel, served over a FastAPI API with
built-in open-core billing.

## Quickstart

Requires Python 3.11+.

```bash
pip install -e ".[dev]"                # core deps + dev tooling
cp .env.example .env                   # then edit — never commit .env
uvicorn api.main:app --reload --port 8000
pytest tests/unit -v                   # run the test suite
```

Optional extras: `pip install -e ".[router]"` (litellm), `.[semantic]`
(chromadb), `.[dev]` (ruff/mypy/pytest).

## API surface

- `GET  /health` — liveness + version
- `GET  /ready` — readiness
- `POST /auth/register` — create tenant + admin user (201)
- `POST /auth/token` — OAuth2 form login → JWT bearer token (24h)
- `GET  /auth/me` — current identity (`sub`, `tenant_id`, `role`)
- `POST /auth/users` — admin-only: invite a member to the tenant
- `GET  /agents` — registered blueprints (name, tier, tools, tags)
- `GET  /agents/{name}` — one blueprint's details
- `POST /chat` — **auth required**; `{"message": "...", "agent": "...?"}` →
  `{reply, intent, model}`; metered per plan (HTTP 429 over allowance)
- `GET  /chat/usage` — today's request count vs plan limit
- `GET  /billing/plans` — pricing tiers (Free / Pro $29 / Enterprise $299)
- `POST /billing/verify/{session_id}` — webhook-free activation: polls
  Stripe, applies the plan to the caller's tenant when paid (403 for
  foreign sessions)
- `POST /billing/checkout/{plan_id}` — Stripe checkout; returns **503**
  until `STRIPE_API_KEY` is set (dev/CI-friendly)

Without `OPENROUTER_API_KEY` the API serves everything except actual
completions — the health/agents/billing surface works with zero external
services.

## Configuration

Copy `.env.example` to `.env`:

| Variable              | Purpose                                          |
|-----------------------|--------------------------------------------------|
| `OPENROUTER_API_KEY`  | OpenRouter key — required for live inference     |
| `OPENROUTER_BASE_URL` | OpenAI-compatible base URL (default openrouter)  |
| `REDIS_URL`           | If set + reachable, memory uses Redis; otherwise in-memory |
| `APP_ENV`             | `development` / `production`                     |
| `APP_SECRET_KEY`      | App secret (change in production)                |
| `STRIPE_API_KEY`      | Enables `POST /billing/checkout/{plan_id}`       |
| `STRIPE_WEBHOOK_SECRET`| Stripe webhook signature verification           |

## Architecture summary

```
api/       FastAPI app + routers (health, agents, chat, billing) + Pydantic schemas
core/
  kernel/inference/   intent → model routing with provider fallback chain
  kernel/memory/      pluggable MemoryStore (in-memory dev / Redis prod)
  agents/factory/     YAML blueprint loader + AgentRegistry
  agents/commanders/  tier 1 — plan → delegate → summarize
  agents/specialists/ tier 2 — persona + bound tools
core/tools/registry.py   typed tool registry (http_fetch built in)
blueprints/          declarative agent YAML
tests/unit/          pytest suite
```

Full details: [docs/architecture.md](docs/architecture.md).
Blueprint authoring: [docs/blueprints.md](docs/blueprints.md).
API reference: [docs/api.md](docs/api.md).

## Agent tier model

| Tier | Name       | Role                          |
|------|------------|-------------------------------|
| 1    | Commander  | plan → delegate → summarize   |
| 2    | Specialist | persona + bound tools         |
| 4    | Guardian   | system integrity (roadmap)    |

## Monetization

Open core: this repo is Apache-2.0. Pricing, tiers, and the upgrade
funnel are documented in [docs/monetization.md](docs/monetization.md)
(mirrored by `GET /billing/plans`).

## License

Apache-2.0. Enterprise features (SSO, Vault integration, audit log) are
commercially licensed in a private overlay repo — see
[docs/monetization.md](docs/monetization.md).
