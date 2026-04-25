# Axiom Rules Engine MCP

An MCP server that exposes the Axiom Rules Engine plus a catalogue of
pre-encoded UK legislation as tools for an LLM.

It lets a Claude session answer "am I entitled to universal credit?" or "what does this reg mean for my household?" by reading the case schema, slot-filling from conversation, running the engine, and citing the relevant statutory source from the trace — rather than guessing.

## Tools

- `list_programmes` — what legislation is in the catalogue today
- `describe_programme(name)` — case schema, outputs, statutory citation, what's out of scope
- `evaluate(name, case, mode, include_trace)` — run a case, return outputs + rule-by-rule trace
- `counterfactual(name, baseline_case, alternative_case)` — run two cases, return deltas per output

Currently encoded: Universal Credit (2025-26), UK income tax (2025-26 main rates), child benefit responsibility under SI 1987/1967 reg 15. Add more by dropping a manifest in `src/axiom_rules_mcp/programmes/` and a translator in `translate.py`.

## Setup

From the repo root, build the engine and sync this package:

```bash
cargo build
uv sync --project mcp
```

The server shells out to `target/debug/axiom-rules` by default. Override with
`AXIOM_RULES_BINARY` if needed.

## Wire up to Claude Code

Add to `~/.claude.json` (or project-scoped `.mcp.json`):

```json
{
  "mcpServers": {
    "axiom-rules": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/absolute/path/to/axiom-rules/mcp",
        "axiom-rules-mcp"
      ]
    }
  }
}
```

Restart Claude Code, then prompts like "I'm thinking about my housing benefit entitlement" will surface the Axiom Rules Engine tools. Use a system prompt that tells Claude to call `list_programmes` first, then `describe_programme`, then slot-fill before `evaluate`.

## Adding a programme

1. Encode the rules in `programmes/<legislation>/<path>/rules.yaml` using the existing DSL.
2. Drop a manifest at `src/axiom_rules_mcp/programmes/<name>.yaml` with:
   - `name`, `title`, `statutory_reference`, `summary`, `rates_effective_from`
   - `programme_path` — relative path to the DSL YAML from the repo root
   - `query_entity` — the entity the query is anchored on
   - `inputs` — user-facing case schema (what the LLM should collect)
   - `outputs` — what the engine returns
   - `out_of_scope` — bullet list of known limitations, so the LLM can caveat honestly
3. Add a translator function in `src/axiom_rules_mcp/translate.py` that maps the user-facing case dict to `(Dataset, ExecutionQuery)`, and register it in `TRANSLATORS`.

The manifest is the LLM's mental model of the programme; keep `summary` and `out_of_scope` concrete so the LLM knows when to refuse vs answer.
