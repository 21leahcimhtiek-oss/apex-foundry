# Architecture

Apex Foundry is a greenfield agentic platform (Path B of Project Chronos):
declarative YAML blueprints become agents, which run on a small kernel of
swappable inference / memory / tools primitives, exposed over FastAPI.

## Layers

```
┌──────────────────────────────────────────────┐
│ api/                HTTP surface             │
│   main.py          app factory (create_app)  │
│   routers/         health, agents, chat, billing
│   schemas/models.py Pydantic request/response│
├──────────────────────────────────────────────┤
│ core/agents/        agent layer              │
│   factory/blueprint.py  YAML loader + registry
│   commanders/base.py    tier 1 orchestration │
│   specialists/base.py   tier 2 execution     │
├──────────────────────────────────────────────┤
│ core/kernel/        platform primitives      │
│   inference/router.py  model routing         │
│   memory/store.py      pluggable MemoryStore │
├──────────────────────────────────────────────┤
│ core/tools/registry.py  typed tool registry  │
└──────────────────────────────────────────────┘
```

### api/ — HTTP surface

`create_app()` in `api/main.py` builds the FastAPI app and mounts four
routers: `health`, `agents`, `chat`, `billing`. No business logic lives
here beyond routing and schema validation — routers delegate to the agent
layer and kernel.

### core/agents/ — agent layer

- **Blueprint factory** (`factory/blueprint.py`): `load_blueprint()` parses
  one YAML file into an `AgentBlueprint` dataclass
  (`agent_id`, `name`, `persona`, `tier`, `model_preference`, `tools`,
  `tags`). `AgentRegistry.load_directory()` loads every `*.yaml` in a
  directory (e.g. `blueprints/`), keyed by `name`. Blueprints are inert
  data — behavior comes from the tier class.
- **Commander** (tier 1): `plan(goal)` asks the model for ≤5 numbered
  steps (intent `research`), `delegate(step)` fans each step out to its
  specialists, `execute(goal)` runs plan → delegate → summarize and
  persists `{steps, summary}` under `mission:<goal>` in memory if one is
  attached.
- **Specialist** (tier 2): `run(task)` performs a single completion with
  the blueprint's persona as the system prompt. If `model_preference`
  isn't `auto`, it is passed as the intent type so inference routes to the
  preferred model class.

Tier mapping in `api/routers/chat.py`: a requested blueprint with
`tier == 1` becomes a `Commander` (with the shared memory store), anything
else becomes a `Specialist`.

### core/kernel/ — primitives

- **Inference** (`kernel/inference/router.py`): every completion goes
  through `complete(prompt, intent_type, system)`. It resolves the intent
  to a model via `MODEL_MAP` (`research` → `openrouter/auto`, `code` →
  `openrouter/anthropic/claude-3.5-sonnet`, `simple`/default →
  `openrouter/openai/gpt-4o-mini`), then walks a fallback chain
  (OpenRouter first, direct OpenAI second) until a provider succeeds;
  raises `RuntimeError` if all fail. `extract_intent()` is a keyword
  heuristic (research/code/simple) pending a real classifier. The client
  is an OpenAI-compatible `openai.OpenAI` pointed at `OPENROUTER_BASE_URL`
  with `OPENROUTER_API_KEY`.
- **Memory** (`kernel/memory/store.py`): agents depend only on the
  `MemoryStore` protocol (`get/set/delete/keys`). `InMemoryStore` is the
  dev/test backend; `RedisStore` JSON-serializes values under an `apex:`
  key prefix. `default_store()` uses Redis when `REDIS_URL` is set **and**
  a ping succeeds, otherwise falls back to in-memory — so dev/CI never
  needs external services.

### core/tools/ — tool registry

`ToolRegistry` holds `Tool(name, description, handler)` objects behind a
typed protocol. One built-in ships: `http_fetch` (HTTP GET via httpx,
15s timeout, body trimmed to 8 000 chars, returns
`{"status", "body"}` JSON). Agents expose `run_tool(name, **kwargs)`;
blueprints declare tool availability by name. A module-level `registry`
with `http_fetch` registered is the default for agents.

## Request flow: POST /chat

1. `ChatRequest` validated (message ≤ 32 000 chars; optional `agent`,
   `intent`).
2. Intent resolved: explicit `req.intent`, else `extract_intent()`
   heuristic on the message.
3. If `agent` is given, look it up in the registry (404 if unknown) and
   instantiate Commander (tier 1, with shared memory) or Specialist.
   Otherwise call `inference.complete()` directly.
4. The exchange is persisted to memory under `chat:last`.
5. Response: `{reply, intent, model}` where `model` is
   `select_model(intent)`.

## Extension points

- New agent: drop a YAML file in `blueprints/` (see
  [blueprints.md](blueprints.md)) — no code required.
- New tool: register a `Tool` on the registry and list it in blueprints.
- New memory backend: implement the `MemoryStore` protocol.
- New provider: append to `FALLBACK_CHAIN` / `MODEL_MAP` in the inference
  router.