"""mcp-tool-bench command line.

  mcp-tool-bench lint "python -m my_server"
  mcp-tool-bench lint https://example.com/mcp --json reports/lint.json
  mcp-tool-bench eval "python -m my_server" --cases examples/cases.yaml --model gpt-4.1-mini
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from .connect import fetch_tools
from .evals import load_cases, openai_chooser, run_cases, summarize
from .github import report_eval, report_lint
from .lint import lint_tools


def _write(path: str | None, data: dict) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2) + "\n")


def cmd_lint(args: argparse.Namespace) -> int:
    info, tools = asyncio.run(fetch_tools(args.server))
    report = lint_tools(tools)
    print(f"{info.get('name', 'server')} {info.get('version', '')} · protocol {info.get('protocolVersion')} · {report.tools} tools")
    for f in report.findings:
        mark = "✗" if f.level == "error" else "!"
        print(f"  {mark} {f.tool:<28} {f.rule:<20} {f.message}")
    print(f"{len(report.errors)} errors, {len(report.warnings)} warnings")
    report_lint(info, report)
    _write(args.json, {"server": info, "tools": report.tools, "findings": [asdict(f) for f in report.findings]})
    return 1 if report.errors or (args.strict and report.warnings) else 0


def cmd_eval(args: argparse.Namespace) -> int:
    _, tools = asyncio.run(fetch_tools(args.server))
    cases = load_cases(args.cases)
    choose = openai_chooser(
        model=args.model,
        base_url=args.base_url or os.environ.get("OPENAI_BASE_URL"),
        api_key=os.environ.get(args.api_key_env) or os.environ.get("OPENAI_API_KEY"),
    )
    results = run_cases(cases, tools, choose)
    for r in results:
        mark = "✓" if r.passed else "✗"
        detail = r.note or ("" if r.passed else f"called {r.called} {json.dumps(r.args)}")
        print(f"  {mark} {r.id:<24} {r.latency_ms:>6} ms  {detail}")
    s = summarize(results)
    print(f"{s['passed']}/{s['cases']} passed · tool accuracy {s['tool_accuracy']:.0%} · args {s['arg_accuracy']:.0%} · p50 {s['p50_ms']} ms")
    report_eval(args.model, s, results)
    _write(args.json, {"model": args.model, "summary": s, "results": [asdict(r) for r in results]})
    return 0 if s["tool_accuracy"] >= args.min_accuracy else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mcp-tool-bench", description="Conformance checks and tool-selection evals for MCP servers")
    sub = p.add_subparsers(dest="cmd", required=True)

    lint = sub.add_parser("lint", help="Check tool names, descriptions and JSON Schema 2020-12 input schemas")
    lint.add_argument("server", help="Server URL, or the command that starts it over stdio")
    lint.add_argument("--json", help="Write a JSON report here")
    lint.add_argument("--strict", action="store_true", help="Fail on warnings too")
    lint.set_defaults(func=cmd_lint)

    ev = sub.add_parser("eval", help="Measure whether a model picks the right tool and arguments")
    ev.add_argument("server", help="Server URL, or the command that starts it over stdio")
    ev.add_argument("--cases", required=True, help="YAML file of prompts and expected tool calls")
    ev.add_argument("--model", required=True, help="Model or deployment name")
    ev.add_argument("--base-url", help="OpenAI-compatible endpoint (Azure OpenAI, GitHub Models, Ollama…)")
    ev.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable holding the API key")
    ev.add_argument("--min-accuracy", type=float, default=0.9, help="Exit non-zero below this tool accuracy (for CI)")
    ev.add_argument("--json", help="Write a JSON report here")
    ev.set_defaults(func=cmd_eval)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except BaseException as e:  # connection failures arrive as ExceptionGroups from anyio
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        root = e
        while isinstance(root, BaseExceptionGroup) and root.exceptions:
            root = root.exceptions[0]
        print(f"error: couldn't talk to the server ({type(root).__name__}: {root})", file=sys.stderr)
        print("Check that the command or URL starts an MCP server on its own.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
