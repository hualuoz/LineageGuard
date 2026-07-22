from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Awaitable, Callable


ToolCall = Callable[[str, dict[str, Any]], Awaitable[Any]]
CORE_DATAHUB_TOOLS = {"get_entities", "list_schema_fields", "get_lineage"}


def decode_tool_result(result: Any) -> Any:
    """Return the JSON payload from an MCP CallToolResult."""
    content = getattr(result, "content", [])
    if getattr(result, "isError", False):
        detail = "\n".join(block.text for block in content if getattr(block, "text", None))
        raise RuntimeError(detail or "DataHub MCP tool failed")

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        # FastMCP wraps list and primitive outputs because structuredContent must
        # have an object root in the MCP protocol.
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured

    for block in content:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue

    raise RuntimeError("DataHub MCP returned no JSON payload")


@asynccontextmanager
async def connect_datahub_mcp(url: str, token: str | None = None) -> AsyncIterator[ToolCall]:
    """Connect to a DataHub Streamable HTTP MCP endpoint."""
    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError as exc:  # pragma: no cover - depends on optional package
        raise RuntimeError('Install MCP support with: pip install -e ".[mcp]"') from exc

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    timeout = httpx.Timeout(30.0, read=300.0)
    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=timeout,
    ) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _,
        ):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools = await session.list_tools()
                available = {tool.name for tool in tools.tools}
                if missing := CORE_DATAHUB_TOOLS - available:
                    raise RuntimeError(f"DataHub MCP is missing required tools: {sorted(missing)}")

                async def call(name: str, arguments: dict[str, Any]) -> Any:
                    result = await session.call_tool(name, arguments=arguments)
                    return decode_tool_result(result)

                yield call
