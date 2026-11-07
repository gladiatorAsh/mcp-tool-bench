"""A small MCP server with deliberately mixed-quality tools, for trying mcp-tool-bench.

    mcp-tool-bench lint "python examples/sample_server.py"
"""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

server = MCPServer("parts-catalog", version="0.1.0")


@server.tool(
    description="Look up a part in the catalog by part number and return its material, mass and current revision.",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def get_part(part_number: str) -> dict:
    return {"part_number": part_number, "material": "6061-T6", "mass_g": 42.0, "revision": "C"}


@server.tool(
    description="Search the catalog for parts whose name or description matches a query. Use this when the user doesn't know the part number.",
    annotations=ToolAnnotations(readOnlyHint=True),
)
def search_parts(query: str, limit: int = 10) -> list[str]:
    return [f"BRK-{i:04d}" for i in range(min(limit, 3))]


@server.tool(description="Release part")  # too vague, and no annotations: lint should flag both
def release(part_number: str, note: str = "") -> str:
    return f"{part_number} released"


if __name__ == "__main__":
    server.run()
