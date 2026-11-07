from mcp_tool_bench.evals import CaseResult
from mcp_tool_bench.github import report_eval, report_lint
from mcp_tool_bench.lint import lint_tools


def test_annotations_and_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    report = lint_tools([{"name": "bad|tool", "description": "", "inputSchema": {"type": "object"}}])
    report_lint({"name": "demo", "version": "1.0", "protocolVersion": "2026-07-28"}, report)
    report_eval("m", {"passed": 0, "cases": 1, "tool_accuracy": 0, "arg_accuracy": 0, "p50_ms": 5, "p95_ms": 5},
                [CaseResult("c1", False, False, False, None, {}, 5, "")])
    out = capsys.readouterr().out
    assert "::error title=MCP lint · name-format::" in out
    assert "::warning title=MCP eval · c1::" in out
    md = summary.read_text()
    assert "### MCP lint · demo 1.0" in md and "bad\\|tool" in md and "0/1 passed" in md


def test_silent_outside_actions(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    report_lint({}, lint_tools([]))
    assert capsys.readouterr().out == ""
