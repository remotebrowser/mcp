from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

kindle_mcp = GatherMCP(brand_id="kindle", name="Kindle MCP")


@kindle_mcp.tool
async def get_book_list() -> dict[str, Any]:
    """Get book list from Amazon Kindle."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.amazon.com/hz/mycd/digital-console/contentlist/booksAll/dateDsc/",
        "kindle_book_list",
    )
