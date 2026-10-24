
import asyncio
import json
from pathlib import Path

from fastmcp import Client

ROOT = Path(__file__).resolve().parent


async def _call_server(server_file, tool_name, arguments):
    server_path = ROOT / "mcp_servers" / server_file

    async with Client(server_path) as client:
        result = await client.call_tool(tool_name, arguments)

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured

    parts = []
    for item in getattr(result, "content", []):
        if getattr(item, "text", None):
            parts.append(item.text)

    if not parts:
        return {"message": "Tool executed without a text result."}

    output = "\n".join(parts)
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return output


def call_mcp_tool(server_file, tool_name, arguments):
    return asyncio.run(
        _call_server(server_file, tool_name, arguments)
    )


def call_ticket_tool(tool_name, arguments):
    return call_mcp_tool(
        "ticket_server.py", tool_name, arguments
    )


def call_leave_tool(tool_name, arguments):
    return call_mcp_tool(
        "leave_server.py", tool_name, arguments
    )
