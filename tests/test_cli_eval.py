import json

from mcp_tool_bench import cli


def test_eval_compares_models(tmp_path, monkeypatch, capsys):
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        "cases:\n"
        "  - {id: lookup, prompt: \"part BRK-1?\", expect_tool: get_part, expect_args: {part_number: BRK-1}}\n"
        "  - {id: needs-missing-tool, prompt: x, expect_tool: add_primitive, requires: [add_primitive]}\n"
        "  - {id: chat, prompt: what is FEA, expect_tool: null}\n"
    )

    def fake_chooser(model, **_):
        good = model == "good-model"
        return lambda prompt, tools, ctx: (("get_part", {"part_number": "BRK-1"}) if prompt.startswith("part") else (None, {})) if good else ("search_parts", {})

    monkeypatch.setattr(cli, "openai_chooser", fake_chooser)
    report = tmp_path / "r.json"
    code = cli.main(["eval", "python examples/sample_server.py", "--cases", str(cases), "--model", "good-model", "--model", "bad-model", "--json", str(report), "--min-accuracy", "0.5"])
    out = capsys.readouterr().out
    data = json.loads(report.read_text())
    assert [r["model"] for r in data["runs"]] == ["good-model", "bad-model"]
    good, bad = (r["summary"] for r in data["runs"])
    assert good["passed"] == 2 and good["skipped"] == 1 and bad["passed"] == 0
    assert "model" in out and "good-model" in out
    assert code == 1  # bad-model is below --min-accuracy
