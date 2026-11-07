"""GitHub Actions output: annotations for each finding and a Markdown job summary.

Active only when running inside Actions (GITHUB_ACTIONS=true), so local output stays plain.
"""

from __future__ import annotations

import os
from typing import Any

from .evals import CaseResult
from .lint import LintReport


def in_actions() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def _esc(s: str) -> str:
    # Workflow command escaping: https://docs.github.com/actions/using-workflows/workflow-commands-for-github-actions
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def _summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(md + "\n")


def report_lint(info: dict[str, Any], report: LintReport) -> None:
    if not in_actions():
        return
    for f in report.findings:
        kind = "error" if f.level == "error" else "warning"
        print(f"::{kind} title=MCP lint · {_esc(f.rule)}::{_esc(f.tool)}: {_esc(f.message)}")

    name = f"{info.get('name', 'server')} {info.get('version', '')}".strip()
    lines = [
        f"### MCP lint · {name}",
        "",
        f"Protocol `{info.get('protocolVersion')}` · {report.tools} tools · **{len(report.errors)} errors**, {len(report.warnings)} warnings",
        "",
    ]
    if report.findings:
        lines += ["| | Tool | Rule | Finding |", "| --- | --- | --- | --- |"]
        for f in report.findings:
            mark = "❌" if f.level == "error" else "⚠️"
            lines.append(f"| {mark} | `{_cell(f.tool)}` | `{f.rule}` | {_cell(f.message)} |")
    else:
        lines.append("✅ No findings.")
    _summary("\n".join(lines))


def report_eval(model: str, summary: dict[str, Any], results: list[CaseResult]) -> None:
    if not in_actions():
        return
    for r in results:
        if not r.passed:
            detail = r.note or f"expected a different call, got {r.called} {r.args}"
            print(f"::warning title=MCP eval · {_esc(r.id)}::{_esc(detail)}")
    lines = [
        f"### MCP tool-selection eval · `{model}`",
        "",
        f"**{summary['passed']}/{summary['cases']} passed** · tool accuracy {summary['tool_accuracy']:.0%} · "
        f"argument accuracy {summary['arg_accuracy']:.0%} · p50 {summary['p50_ms']} ms · p95 {summary['p95_ms']} ms",
        "",
        "| | Case | Called | Latency |",
        "| --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(f"| {'✅' if r.passed else '❌'} | `{_cell(r.id)}` | `{r.called or '(no tool)'}` | {r.latency_ms} ms |")
    _summary("\n".join(lines))
