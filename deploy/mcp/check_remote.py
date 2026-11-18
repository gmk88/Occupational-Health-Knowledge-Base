"""Verify a public MCP endpoint with a real API key.

Example:
    .\\.venv\\Scripts\\python.exe ..\\deploy\\mcp\\check_remote.py ^
        --url https://kb.guanmingkun.ltd/mcp/ ^
        --key-file ..\\var\\mcp\\clients\\customer-a\\key.txt
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def check(url: str, key: str) -> None:
    async with streamablehttp_client(
        url, headers={"Authorization": f"Bearer {key}"}
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [tool.name for tool in tools.tools])
            result = await session.call_tool("list_taxonomy", {})
            print("taxonomy ok:", "categories" in result.content[0].text)


def main() -> None:
    default_key = Path(__file__).resolve().parents[2] / "var" / "mcp" / "mcp_key.txt"
    parser = argparse.ArgumentParser(description="Check a remote MCP endpoint")
    parser.add_argument(
        "--url",
        default="https://kb.guanmingkun.ltd/mcp/",
        help="MCP endpoint（默认 https://kb.guanmingkun.ltd/mcp/）",
    )
    parser.add_argument(
        "--key-file",
        default=str(default_key),
        help="file containing the key（默认 var/mcp/mcp_key.txt）",
    )
    parser.add_argument("--key", default=None, help="key value (overrides --key-file)")
    args = parser.parse_args()
    key = args.key or Path(args.key_file).read_text(encoding="ascii").strip()
    asyncio.run(check(args.url.rstrip("/") + "/", key))


if __name__ == "__main__":
    main()
