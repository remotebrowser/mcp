import asyncio
from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

goodreads_mcp = GatherMCP(brand_id="goodreads", name="Goodreads MCP")


@goodreads_mcp.tool
async def get_book_list() -> dict[str, Any]:
    """Get the book list from a user's Goodreads account."""
    return await zen_dpage_mcp_tool(
        "https://www.goodreads.com/review/list?ref=nav_mybooks&view=table", "goodreads_book_list"
    )


@goodreads_mcp.tool(task=True)
async def slow_computation(duration: int) -> str:
    """A long-running operation."""
    for _i in range(duration):
        await asyncio.sleep(1)
    return f"Completed in {duration} seconds"
