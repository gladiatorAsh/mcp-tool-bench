"""Keeps the CAD benchmark honest: every expected tool and argument must exist in the CAD servers' schemas.

benchmarks/cad/tool-vocabulary.json is a snapshot of the tool schemas of freecad-mcp-server and
fusion-mcp-server. Regenerate it when those servers change their tools.
"""

import json
from pathlib import Path

from mcp_tool_bench.evals import load_cases

HERE = Path(__file__).parent.parent / "benchmarks" / "cad"
CASES = load_cases(HERE / "cases.yaml")
VOCAB = json.loads((HERE / "tool-vocabulary.json").read_text())
SHARED = set.intersection(*(set(v) for v in VOCAB.values()))


def test_case_ids_unique():
    assert len({c.id for c in CASES}) == len(CASES)


def test_expected_tools_and_args_exist():
    for c in CASES:
        servers = [s for s, tools in VOCAB.items() if all(r in tools for r in c.requires)]
        assert servers, f"{c.id}: no CAD server has {c.requires}"
        for server in servers:
            tools = VOCAB[server]
            expected = [t for t in c.expect_tool if t]
            assert all(t in tools for t in expected), f"{c.id}: {server} lacks one of {expected}"
            primary = c.expect_tool[0]
            if primary and c.expect_args:
                unknown = set(c.expect_args) - set(tools[primary])
                assert not unknown, f"{c.id}: {primary} on {server} has no argument(s) {unknown}"


def test_cases_without_requires_only_use_shared_tools():
    for c in CASES:
        if not c.requires:
            assert all(t in SHARED for t in c.expect_tool if t), f"{c.id} uses a tool not every CAD server has; add `requires`"
