"""Splunk MCP backend — connects via mcp-remote to the Splunk MCP Server HTTP endpoint."""
from __future__ import annotations

import logging
import shutil
from typing import Any

from google.genai import types

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import Tool as MCPTool
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False
    ClientSession = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment,misc]
    stdio_client = None  # type: ignore[assignment]
    MCPTool = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class SplunkMCPBackend:
    """
    Connects to the Splunk MCP Server using `mcp-remote` as a stdio proxy.

    The Splunk MCP Server exposes an HTTP endpoint; `mcp-remote` (via npx)
    bridges it to the MCP stdio protocol that the Python MCP SDK expects.

    Connection config:
        command: npx
        args: [-y, mcp-remote, <endpoint>, --header, Authorization: Bearer <token>]
    """

    def __init__(self, endpoint: str, token: str) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._session: ClientSession | None = None
        self._stdio_cm = None

    @staticmethod
    def is_available() -> bool:
        return _MCP_AVAILABLE and shutil.which("npx") is not None

    async def __aenter__(self) -> "SplunkMCPBackend":
        if not _MCP_AVAILABLE:
            raise RuntimeError(
                "The 'mcp' Python package is not installed. Run: pip install mcp"
            )
        if not shutil.which("npx"):
            raise RuntimeError(
                "npx not found. Install Node.js >=18 to use mcp-remote."
            )

        logger.info(
            "Connecting to Splunk MCP Server at %s (via mcp-remote)…", self._endpoint
        )
        server_params = StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "mcp-remote",
                self._endpoint,
                "--header",
                f"Authorization: Bearer {self._token}",
            ],
        )
        self._stdio_cm = stdio_client(server_params)
        read, write = await self._stdio_cm.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        logger.debug("Splunk MCP session initialized")
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._session:
            await self._session.__aexit__(*exc_info)
        if self._stdio_cm:
            await self._stdio_cm.__aexit__(*exc_info)

    async def list_tools_as_gemini(self) -> list[types.Tool]:
        assert self._session is not None
        result = await self._session.list_tools()
        declarations = [_to_gemini(t) for t in result.tools]
        logger.debug("Loaded %d tools from Splunk MCP Server", len(declarations))
        return [types.Tool(function_declarations=declarations)]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        assert self._session is not None
        result = await self._session.call_tool(name, arguments)
        if result.isError:
            logger.warning("Splunk MCP tool %r returned an error", name)
        return "\n".join(
            item.text if hasattr(item, "text") else str(item)
            for item in result.content
        )


def _to_gemini(tool: MCPTool) -> types.FunctionDeclaration:
    schema = tool.inputSchema or {}
    properties: dict[str, types.Schema] = {
        name: types.Schema(
            type=_jtype(defn.get("type", "string")),
            description=defn.get("description", ""),
        )
        for name, defn in schema.get("properties", {}).items()
    }
    return types.FunctionDeclaration(
        name=tool.name,
        description=tool.description or "",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties=properties,
            required=schema.get("required", []),
        ),
    )


def _jtype(t: str) -> types.Type:
    return {
        "string": types.Type.STRING,
        "integer": types.Type.INTEGER,
        "number": types.Type.NUMBER,
        "boolean": types.Type.BOOLEAN,
        "array": types.Type.ARRAY,
        "object": types.Type.OBJECT,
    }.get(t, types.Type.STRING)
