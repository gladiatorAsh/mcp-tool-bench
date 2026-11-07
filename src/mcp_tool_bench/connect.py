"""Fetch a server's tool catalog over stdio or Streamable HTTP using the official MCP Python SDK (2.x)."""

from __future__ import annotations

import os
import shlex
from typing import Any

from mcp import StdioServerParameters
from mcp.client.client import Client


def _target(server: str):
    # A URL means a remote server; anything else is a command line to launch over stdio.
    if server.startswith(("http://", "https://")):
        return server
    parts = shlex.split(server)
    # Pass the caller's environment through so PATH, PYTHONPATH and API keys reach the server.
    return StdioServerParameters(command=parts[0], args=parts[1:], env=dict(os.environ))


async def fetch_tools(server: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return (server_info, tools). `server` is a URL, a command line, or an in-process MCPServer (for tests)."""
    target = _target(server) if isinstance(server, str) else server
    async with Client(target) as client:
        result = await client.list_tools()
        tools = [t.model_dump(by_alias=True, exclude_none=True) for t in result.tools]
        info = client.server_info.model_dump(exclude_none=True) if client.server_info else {}
        info["protocolVersion"] = client.protocol_version
    return info, tools
