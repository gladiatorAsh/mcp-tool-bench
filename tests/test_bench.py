from examples.sample_server import server
from mcp_tool_bench.connect import fetch_tools
from mcp_tool_bench.evals import Case, _matches, run_cases, summarize
from mcp_tool_bench.lint import lint_tools


async def test_lint_sample_server_in_process():
    info, tools = await fetch_tools(server)
    assert info["name"] == "parts-catalog"
    report = lint_tools(tools)
    rules = {(f.tool, f.rule) for f in report.findings}
    assert ("release", "description-short") in rules
    assert ("release", "annotations-missing") in rules
    assert not any(f.tool == "get_part" and f.level == "error" for f in report.findings)


def test_lint_catches_bad_schemas():
    tools = [
        {"name": "bad name!", "description": "x" * 30, "inputSchema": {"type": "object"}},
        {"name": "t2", "description": "Does a thing for testing purposes", "inputSchema": {"type": "object", "required": ["a"]}},
        {"name": "t3", "description": "Does a thing for testing purposes", "inputSchema": {"type": "objekt"}},
        {"name": "T2", "description": "Duplicate name in a different case", "inputSchema": {"type": "object"}},
    ]
    rules = {(f.tool, f.rule) for f in lint_tools(tools).findings}
    assert ("bad name!", "name-format") in rules
    assert ("t2", "required-unknown") in rules
    assert ("t3", "schema-invalid") in rules
    assert ("t2", "name-duplicate") in rules


def test_arg_matching():
    assert _matches({"q": "~bracket"}, {"q": "aluminium mounting Brackets", "limit": 5})
    assert _matches({"n": 3}, {"n": 3.0})
    assert not _matches({"n": "BRK-1"}, {"n": "BRK-2"})
    assert not _matches({"missing": 1}, {})


def test_run_cases_with_fake_model():
    tools = [{"name": "get_part", "inputSchema": {"type": "object"}}, {"name": "search_parts", "inputSchema": {"type": "object"}}]
    cases = [
        Case("a", "part BRK-1?", "get_part", {"part_number": "BRK-1"}),
        Case("b", "find brackets", "search_parts", {"query": "~bracket"}),
        Case("c", "what is FEA", None),
        Case("d", "ghost", "not_a_tool"),
    ]
    answers = {"part BRK-1?": ("get_part", {"part_number": "brk-1"}), "find brackets": ("get_part", {}), "what is FEA": (None, {})}
    results = run_cases(cases, tools, lambda p, _t: answers[p])
    assert [r.passed for r in results] == [True, False, True, False]
    s = summarize(results)
    assert s["passed"] == 2 and s["tool_accuracy"] == 0.5
