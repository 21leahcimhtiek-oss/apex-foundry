# Apex Foundry

Greenfield agentic platform (Path B of Project Chronos). Declarative
blueprint-defined agents — commanders, specialists, guardians — on a
pluggable inference + memory kernel, served over a FastAPI API with
built-in open-core billing.

## Architecture

```
apex-foundry/
├── api/
│   ├── main.py                  # FastAPI app factory
│   ├── routers/                 # health, agents, chat, billing
│   └── schemas/                 # Pydantic models
├── core/
│   ├── kernel/inference/        # intent → model routing + fallback chain
│   ├── kernel/memory/           # pluggable MemoryStore (in-mem / Redis)
│   ├── agents/
│   │   ├── factory/             # YAML blueprints + registry
│   │   ├── commanders/          # tier 1 — plan → delegate → summarize
│   │   └── specialists/         # tier 2 — persona + bound tools
│   └── tools/                   # tool registry (http_fetch built-in)
├── blueprints/                  # declarative agent YAML
└── tests/unit/
```

## Quickstart

```bash
pip install -e ".[dev]"
uvicorn api.main:app --reload --port 8000
pytest tests/unit -v
```

- `GET  /health` — liveness
- `GET  /agents` — registered blueprints
- `POST /chat`   — `{"message": "...", "agent": "Research Specialist"?}`
- `GET  /billing/plans` — pricing tiers

Set `OPENROUTER_API_KEY` (see `.env.example`) for live inference; without
it the API serves everything except actual completions.

## Agent tier model

| Tier | Name       | Role                          |
|------|------------|-------------------------------|
| 1    | Commander  | plan → delegate → summarize   |
| 2    | Specialist | persona + bound tools         |
| 4    | Guardian   | system integrity (roadmap)    |

## License

Open core: core is Apache-2.0; enterprise features (SSO, Vault integration,
audit log) are commercially licensed. See `MONETIZATION.md`.
