# CAD agent benchmark

45 realistic requests a mechanical engineer would make to a CAD agent, each with the first tool call a good agent should make.

| Area | Cases | What it tests |
| --- | --- | --- |
| Inspect | 6 | Picking the read-only tool that answers the question |
| Edit | 10 | Looking before acting when parameter names are unknown; correct names, values, units and expressions when they're known |
| Measure | 6 | Mass properties, with domain knowledge (steel density, area for coating quotes) |
| Export | 7 | STEP for vendors, STL for printing, job polling |
| Model | 8 | Primitives and booleans, including diameter-to-radius conversion |
| Open | 2 | Native files and STEP import |
| No tool | 5 | Answering engineering questions directly instead of calling tools |
| Safety | 1 | Not improvising a destructive action when no tool supports it |

Cases only use tools that [freecad-mcp-server](https://github.com/gladiatorAsh/freecad-mcp-server) and [fusion-mcp-server](https://github.com/gladiatorAsh/fusion-mcp-server) share, unless they declare `requires`. Cases are skipped on servers without those tools. `tool-vocabulary.json` is a snapshot of both servers' schemas, and a test checks every case against it.

## Run it

```bash
pip install "mcp-tool-bench[eval]" freecad-mcp-server
mcp-tool-bench eval "python -m freecad_mcp" --cases benchmarks/cad/cases.yaml \
  --model openai/gpt-4.1-mini --model openai/gpt-4o-mini \
  --base-url https://models.github.ai/inference --api-key-env GITHUB_TOKEN --delay 4
```

The [CAD benchmark workflow](../../.github/workflows/cad-benchmark.yml) runs it weekly on GitHub Models and uploads the JSON reports.

## Scoring

Each case checks the model's **first** tool call: whether the tool is right (tool accuracy), and whether the arguments match the expected subset (argument accuracy). Multi-step behaviour, like editing a parameter after listing them, is covered by giving the model the design state in `context`.
