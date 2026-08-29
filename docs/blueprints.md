# Blueprint authoring

Agents in Apex Foundry are declarative YAML blueprints. A blueprint is
pure data; the platform turns it into a Commander (tier 1) or Specialist
(tier 2) at runtime. No Python required.

## Schema

`core/agents/factory/blueprint.py` — `load_blueprint()`:

| Field              | Type       | Required | Default  | Notes                              |
|--------------------|------------|----------|----------|------------------------------------|
| `agent_id`         | string     | yes      | —        | stable identifier (e.g. `cmd-ops-001`) |
| `name`             | string     | yes      | —        | registry key / API lookup name     |
| `persona`          | string     | no       | `""`     | system prompt for the agent        |
| `tier`             | int        | no       | `2`      | 0=Aurora, 1=Commander, 2=Specialist, 3=Micro, 4=Guardian |
| `model_preference` | string     | no       | `auto`   | intent type for model routing; `auto` lets inference pick |
| `tools`            | list[str]  | no       | `[]`     | tool names from the tool registry  |
| `tags`             | list[str]  | no       | `[]`     | free-form labels                   |

## Loading

- `AgentRegistry.load_directory("blueprints")` loads every `*.yaml` in the
  directory (sorted) into the module-level `registry`, keyed by `name`.
- Duplicate `name`s: last file (alphabetically) wins.
- `GET /agents` lists everything registered; `POST /chat` with
  `"agent": "<name>"` routes to it.

## Examples

`blueprints/ops-commander.yaml` — a Commander (tier 1):

```yaml
agent_id: cmd-ops-001
name: Ops Commander
tier: 1
persona: "You are the Ops Commander. Break operational goals into precise, executable steps and delegate ruthlessly."
model_preference: auto
tools: [http_fetch]
tags: [ops, commander]
```

`blueprints/research-specialist.yaml` — a Specialist (tier 2) that pins
the model class to `research` via `model_preference`:

```yaml
agent_id: spec-research-001
name: Research Specialist
tier: 2
persona: "You are a research specialist. Answer with dense, sourced, verifiable facts."
model_preference: research
tools: [http_fetch]
tags: [research]
```

## How tiers behave at runtime

- **Commander (tier 1)**: `/chat` calls `execute(goal)` →
  plan (≤5 steps, intent `research`) → delegate each step to its
  specialists → summarize (intent `simple`) → persist to memory under
  `mission:<goal>`.
- **Specialist (tier 2)**: single completion with the persona as system
  prompt; `model_preference` (when not `auto`) is used as the intent type
  for model selection.

## Tips

- Keep personas specific and behavioral — they become the system prompt.
- Use `model_preference: research` for analysis-heavy agents, `simple`
  for cheap/fast ones, `code` for coding agents; leave `auto` unless you
  have a reason.
- Only list tools that exist in the tool registry (built-in:
  `http_fetch`). Unlisted-but-registered tools can still be invoked via
  `run_tool`; the `tools` list is declarative intent / surface.
- Tags are for your own filtering (e.g. `by_tier` + tags dashboards).