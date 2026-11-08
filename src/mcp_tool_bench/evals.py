"""Tool-selection evals: does a model pick the right tool, with the right arguments, for a prompt?

The model is reached through any OpenAI-compatible chat completions endpoint, so the same
cases run against Azure OpenAI, GitHub Models (free tier), Ollama or OpenAI itself.

A case checks the model's *first* tool call, which is what a single prompt can fairly test.
For requests that need a look before acting ("make it 25 mm wide" with no parameter names
known yet), list every acceptable first step in `expect_tool`.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass
class Case:
    id: str
    prompt: str
    expect_tool: list[str | None]  # acceptable first calls; None means "answer without a tool"
    expect_args: dict[str, Any] = field(default_factory=dict)
    context: str = ""  # design state shown to the model before the prompt
    requires: list[str] = field(default_factory=list)  # skip the case unless the server has these tools
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.expect_tool = _as_list(self.expect_tool)


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
    skipped: bool = False
    tags: list[str] = field(default_factory=list)


def _as_list(v: Any) -> list[str | None]:
    return list(v) if isinstance(v, list) else [v]


def load_cases(path: str | Path) -> list[Case]:
    data = yaml.safe_load(Path(path).read_text())
    shared_context = data.get("context", "")
    cases = []
    for i, c in enumerate(data.get("cases", [])):
        expected = _as_list(c.get("expect_tool"))
        cases.append(
            Case(
                id=str(c.get("id", i + 1)),
                prompt=c["prompt"],
                expect_tool=expected,
                expect_args=c.get("expect_args") or {},
                context=c.get("context", shared_context),
                requires=c.get("requires") or [],
                tags=c.get("tags") or [],
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
    Strings match case-insensitively and ignore surrounding spaces; a string starting with '~' matches if it's
    contained in the actual value; a list of alternatives can be written as {"any": [...]}; numbers match to 1e-6."""
    if isinstance(expected, dict) and set(expected) == {"any"}:
        return any(_matches(e, actual) for e in expected["any"])
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _matches(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(_matches(e, a) for e, a in zip(expected, actual))
    if isinstance(expected, str) and isinstance(actual, str):
        if expected.startswith("~"):
            return expected[1:].strip().lower() in actual.lower()
        return " ".join(expected.lower().split()) == " ".join(actual.lower().split())
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if isinstance(actual, str):
            try:
                actual = float(actual)
            except ValueError:
                return False
        return isinstance(actual, (int, float)) and abs(expected - actual) < 1e-6
    return expected == actual


# A "chooser" takes (prompt, openai_tools, context) and returns (tool_name | None, args).
Chooser = Callable[[str, list[dict[str, Any]], str], tuple[str | None, dict[str, Any]]]

SYSTEM = "You are an engineering assistant connected to CAD tools. Use a tool when the request needs one; answer directly when it doesn't."


def openai_chooser(model: str, base_url: str | None = None, api_key: str | None = None, system: str = SYSTEM, retries: int = 5) -> Chooser:
    from openai import APIStatusError, OpenAI, RateLimitError  # lazy: lint works without the eval extra

    headers = {}
    if base_url and "models.github.ai" in base_url:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0, default_headers=headers)

    def choose(prompt: str, tools: list[dict[str, Any]], context: str = ""):
        messages = [{"role": "system", "content": system + (f"\n\nCurrent design state:\n{context.strip()}" if context else "")}]
        messages.append({"role": "user", "content": prompt})
        for attempt in range(retries + 1):
            try:
                raw = client.chat.completions.with_raw_response.create(model=model, messages=messages, tools=tools, tool_choice="auto", temperature=0)
                resp = raw.parse()
                if isinstance(resp, str) or not hasattr(resp, "choices"):
                    http = raw.http_response
                    body = http.text[:300].replace("\n", " ")
                    raise RuntimeError(f"unexpected response: HTTP {http.status_code}, {http.headers.get('content-type')}: {body}")
                break
            except (RateLimitError, APIStatusError) as e:
                status = getattr(e, "status_code", 429)
                if attempt == retries or status not in (429, 500, 502, 503):
                    raise
                retry_after = float(getattr(e, "response", None) and e.response.headers.get("retry-after") or 0)
                time.sleep(max(retry_after, 2**attempt) + random.random())
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


def run_cases(cases: list[Case], tools: list[dict[str, Any]], choose: Chooser, delay_s: float = 0.0) -> list[CaseResult]:
    oa_tools = to_openai_tools(tools)
    known = {t["name"] for t in tools}
    results = []
    for case in cases:
        missing = [t for t in case.requires if t not in known]
        if missing:
            results.append(CaseResult(case.id, False, False, False, None, {}, 0, f"skipped: server has no {', '.join(missing)}", skipped=True, tags=case.tags))
            continue
        unknown = [t for t in case.expect_tool if t and t not in known]
        if len(unknown) == len([t for t in case.expect_tool if t]) and unknown:
            results.append(CaseResult(case.id, False, False, False, None, {}, 0, f"expected tool {unknown[0]!r} isn't on the server", tags=case.tags))
            continue
        start = time.perf_counter()
        try:
            called, args = choose(case.prompt, oa_tools, case.context)
            note = ""
        except Exception as e:  # a failed request is a failed case, not a crashed run
            called, args, note = None, {}, f"request failed: {e}"
        ms = int((time.perf_counter() - start) * 1000)
        tool_ok = called in case.expect_tool and not note
        # Argument expectations apply to the primary expected tool (the first one listed).
        args_ok = tool_ok and (called != case.expect_tool[0] or _matches(case.expect_args, args))
        results.append(CaseResult(case.id, tool_ok and args_ok, tool_ok, args_ok, called, args, ms, note, tags=case.tags))
        if delay_s:
            time.sleep(delay_s)
    return results


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    ran = [r for r in results if not r.skipped]
    n = len(ran) or 1
    lat = sorted(r.latency_ms for r in ran) or [0]
    by_tag: dict[str, list[int]] = {}
    for r in ran:
        for t in r.tags:
            by_tag.setdefault(t, [0, 0])
            by_tag[t][0] += r.passed
            by_tag[t][1] += 1
    return {
        "cases": len(ran),
        "skipped": len(results) - len(ran),
        "passed": sum(r.passed for r in ran),
        "tool_accuracy": round(sum(r.tool_ok for r in ran) / n, 3),
        "arg_accuracy": round(sum(r.args_ok for r in ran) / n, 3),
        "p50_ms": lat[len(lat) // 2],
        "p95_ms": lat[min(len(lat) - 1, int(len(lat) * 0.95))],
        "by_tag": {t: {"passed": p, "cases": c} for t, (p, c) in sorted(by_tag.items())},
    }
