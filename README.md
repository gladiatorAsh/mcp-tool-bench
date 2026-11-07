# mcp-tool-bench

**Conformance checks and tool-selection evals for MCP servers.**

An MCP server can pass its unit tests and still fail in practice. The model picks the wrong tool, fills arguments badly, or a host can't tell a read from a delete. `mcp-tool-bench` tests the server the way a model sees it: through its tool catalog.

- **`lint`** connects to any server (stdio or Streamable HTTP) and checks tool names, descriptions, annotations, and that every input schema is valid **JSON Schema 2020-12**, which the 2026-07-28 spec now requires.
- **`eval`** runs a set of prompts against a model and measures whether it calls the right tool with the right arguments. It reports tool accuracy, argument accuracy and latency. Any OpenAI-compatible endpoint works: Azure OpenAI, GitHub Models (free tier), Ollama or OpenAI itself.

> **Status: early.** `lint` and the eval engine work and are tested. Next up are multi-model comparison reports and a GitHub Action. See the [roadmap](#roadmap).

## Quick start

```bash
pip install -e ".[eval,dev]"

# Lint the bundled sample server (launched over stdio)
mcp-tool-bench lint "python examples/sample_server.py"
```

```
parts-catalog 0.1.0 · protocol 2026-07-28 · 3 tools
  ! get_part      param-undescribed    Parameter 'part_number' has no description
  ! release       description-short    Description is 12 characters; say what it does and when to use it
  ! release       annotations-missing  No readOnlyHint/destructiveHint, so hosts can't tell if this tool changes anything
  …
0 errors, 7 warnings
```

Run tool-selection evals, for example on the GitHub Models free tier:

```bash
export GITHUB_TOKEN=...   # a token with models:read
mcp-tool-bench eval "python examples/sample_server.py" \
  --cases examples/cases.yaml \
  --model openai/gpt-4.1-mini \
  --base-url https://models.github.ai/inference \
  --api-key-env GITHUB_TOKEN \
  --json reports/eval.json
```

Cases are plain YAML. `expect_args` is a subset match, and `~` means "contains":

```yaml
cases:
  - id: search-by-description
    prompt: Find me the aluminium mounting brackets.
    expect_tool: search_parts
    expect_args: { query: "~bracket" }
  - id: no-tool-needed
    prompt: What does FEA stand for?
    expect_tool: null
```

Both commands exit non-zero on failure (`--strict` for lint warnings, `--min-accuracy` for evals), so they drop straight into CI.

## What lint checks

| Rule | Level | Why it matters |
| --- | --- | --- |
| `name-format`, `name-duplicate` | error | Hosts and models address tools by name |
| `description-missing` / `-short` / `-long` | error / warning | The description is how the model decides when to call a tool, and every character costs context |
| `schema-invalid`, `schema-root-type`, `required-unknown` | error | Invalid JSON Schema 2020-12 is rejected by 2026-07-28 clients |
| `param-undescribed`, `param-untyped` | warning | Undescribed parameters are where argument errors come from |
| `annotations-missing` | warning | Without `readOnlyHint`/`destructiveHint`, hosts can't decide what needs confirmation |

## Roadmap

- [x] `lint` over stdio and Streamable HTTP with the MCP Python SDK 2.x
- [x] `eval` engine: subset argument matching, accuracy and latency summary, JSON reports
- [x] Tests, including an in-process server
- [ ] Compare several models in one run and write an HTML report
- [ ] GitHub Action: lint and eval on every PR to an MCP server repo
- [ ] Protocol conformance probes: stateless requests, `tools/list` caching (`ttlMs`), Tasks lifecycle
- [ ] Generate starter cases from the tool catalog with a model, then review them by hand
- [ ] Run against popular public MCP servers and publish the results

## Related

- [fusion-mcp-server](https://github.com/gladiatorAsh/fusion-mcp-server) and [mcp-cad-viewer](https://github.com/gladiatorAsh/mcp-cad-viewer) are benchmarked with this tool.

## License

MIT © Ashutosh Singh
