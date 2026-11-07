"""Tool-selection evals: does a model pick the right tool, with the right arguments, for a prompt?

The model is reached through any OpenAI-compatible chat completions endpoint, so the same
cases run against Azure OpenAI, GitHub Models (free tier), Ollama or OpenAI itself.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass
class Case:
    id: str
    prompt: str
    expect_tool: str | None  # None means "the model should not call any tool"
    expect_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseResult:
    id: str
    passed: bool
    tool_ok: bool
    args_ok: bool
    called: str | None
    args: dict[str, Any]
    latency_ms: int
    note: str = ""


def load_cases(path: str | Path) -> list[Case]:
    data = yaml.safe_load(Path(path).read_text())
    cases = []
    for i, c in enumerate(data.get("cases", [])):
        cases.append(
            Case(
                id=str(c.get("id", i + 1)),
                prompt=c["prompt"],
                expect_tool=c.get("expect_tool"),
                expect_args=c.get("expect_args") or {},
            )
        )
    return cases


def to_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description") or "",
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
            },
        }
        for t in tools
    ]


def _matches(expected: Any, actual: Any) -> bool:
    """Expected values are a subset check: every expected key must match; extra args are fine.
    Strings match case-insensitively; a string starting with '~' matches if it's contained in the actual value."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _matches(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(_matches(e, a) for e, a in zip(expected, actual))
    if isinstance(expected, str) and isinstance(actual, str):
        if expected.startswith("~"):
            return expected[1:].lower() in actual.lower()
        return expected.lower() == actual.lower()
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)) and not isinstance(expected, bool):
        return abs(expected - actual) < 1e-9
    return expected == actual


# A "chooser" takes (prompt, openai_tools) and returns (tool_name | None, args).
Chooser = Callable[[str, list[dict[str, Any]]], tuple[str | None, dict[str, Any]]]


def openai_chooser(model: str, base_url: str | None = None, api_key: str | None = None, system: str | None = None) -> Chooser:
    from openai import OpenAI  # imported lazily so lint works without the eval extra

    client = OpenAI(base_url=base_url, api_key=api_key)

    def choose(prompt: str, tools: list[dict[str, Any]]):
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        resp = client.chat.completions.create(model=model, messages=messages, tools=tools, tool_choice="auto", temperature=0)
        calls = resp.choices[0].message.tool_calls or []
        if not calls:
            return None, {}
        fn = calls[0].function
        try:
            args = json.loads(fn.arguments or "{}")
        except json.JSONDecodeError:
            args = {"__unparseable__": fn.arguments}
        return fn.name, args

    return choose


def run_cases(cases: list[Case], tools: list[dict[str, Any]], choose: Chooser) -> list[CaseResult]:
    oa_tools = to_openai_tools(tools)
    known = {t["name"] for t in tools}
    results = []
    for case in cases:
        if case.expect_tool and case.expect_tool not in known:
            results.append(CaseResult(case.id, False, False, False, None, {}, 0, f"expected tool '{case.expect_tool}' isn't on the server"))
            continue
        start = time.perf_counter()
        try:
            called, args = choose(case.prompt, oa_tools)
            note = ""
        except Exception as e:  # a failed request is a failed case, not a crashed run
            called, args, note = None, {}, f"request failed: {e}"
        ms = int((time.perf_counter() - start) * 1000)
        tool_ok = called == case.expect_tool and not note
        args_ok = tool_ok and _matches(case.expect_args, args)
        results.append(CaseResult(case.id, tool_ok and args_ok, tool_ok, args_ok, called, args, ms, note))
    return results


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    n = len(results) or 1
    lat = sorted(r.latency_ms for r in results) or [0]
    return {
        "cases": len(results),
        "passed": sum(r.passed for r in results),
        "tool_accuracy": round(sum(r.tool_ok for r in results) / n, 3),
        "arg_accuracy": round(sum(r.args_ok for r in results) / n, 3),
        "p50_ms": lat[len(lat) // 2],
        "p95_ms": lat[min(len(lat) - 1, int(len(lat) * 0.95))],
    }
