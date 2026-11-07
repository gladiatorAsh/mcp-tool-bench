"""Static checks on an MCP server's tool catalog.

These are the problems that make models pick the wrong tool or send bad arguments,
plus the schema rules the 2026-07-28 spec tightened (input schemas are JSON Schema 2020-12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
MIN_DESCRIPTION = 20
MAX_DESCRIPTION = 1024


@dataclass
class Finding:
    tool: str
    level: str  # "error" | "warning"
    rule: str
    message: str


@dataclass
class LintReport:
    tools: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]


def _walk_properties(schema: dict[str, Any], path: str = ""):
    for name, prop in (schema.get("properties") or {}).items():
        if isinstance(prop, dict):
            yield f"{path}{name}", prop
            if prop.get("type") == "object":
                yield from _walk_properties(prop, f"{path}{name}.")


def lint_tools(tools: list[dict[str, Any]]) -> LintReport:
    """Lint tools given as plain dicts with name, description, inputSchema and optional annotations."""
    report = LintReport(tools=len(tools))
    add = report.findings.append
    seen: dict[str, int] = {}

    for tool in tools:
        name = tool.get("name") or "<unnamed>"
        seen[name.lower()] = seen.get(name.lower(), 0) + 1

        if not NAME_RE.match(name):
            add(Finding(name, "error", "name-format", "Tool names should be 1-64 characters of letters, digits, '_', '-' or '.'"))

        desc = (tool.get("description") or "").strip()
        if not desc:
            add(Finding(name, "error", "description-missing", "No description, so the model has to guess when to use this tool"))
        elif len(desc) < MIN_DESCRIPTION:
            add(Finding(name, "warning", "description-short", f"Description is {len(desc)} characters; say what it does and when to use it"))
        elif len(desc) > MAX_DESCRIPTION:
            add(Finding(name, "warning", "description-long", f"Description is {len(desc)} characters and costs context on every request"))

        schema = tool.get("inputSchema")
        if not isinstance(schema, dict):
            add(Finding(name, "error", "schema-missing", "inputSchema is missing or not an object"))
            continue
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as e:
            add(Finding(name, "error", "schema-invalid", f"Not valid JSON Schema 2020-12: {e.message}"))
            continue
        if schema.get("type") != "object":
            add(Finding(name, "error", "schema-root-type", "inputSchema must have type 'object'"))

        props = schema.get("properties") or {}
        missing = [r for r in schema.get("required", []) if r not in props]
        if missing:
            add(Finding(name, "error", "required-unknown", f"'required' lists properties that don't exist: {', '.join(missing)}"))

        for path, prop in _walk_properties(schema):
            if not prop.get("description") and "enum" not in prop and "const" not in prop:
                add(Finding(name, "warning", "param-undescribed", f"Parameter '{path}' has no description"))
            if not any(k in prop for k in ("type", "enum", "const", "anyOf", "oneOf", "allOf", "$ref")):
                add(Finding(name, "warning", "param-untyped", f"Parameter '{path}' has no type, so any value is accepted"))

        ann = tool.get("annotations") or {}
        if not any(k in ann for k in ("readOnlyHint", "destructiveHint")):
            add(Finding(name, "warning", "annotations-missing", "No readOnlyHint/destructiveHint, so hosts can't tell if this tool changes anything"))

    for lname, count in seen.items():
        if count > 1:
            add(Finding(lname, "error", "name-duplicate", f"{count} tools share this name (case-insensitive)"))

    return report
