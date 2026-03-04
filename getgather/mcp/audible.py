from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

audible_mcp = GatherMCP(brand_id="audible", name="Audible MCP")


@audible_mcp.tool
async def get_book_list() -> dict[str, Any]:
    """Get book list from Audible.com."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.audible.com/library/titles",
        "audible_book_list",
    )


@audible_mcp.tool
async def get_wishlist() -> dict[str, Any]:
    """Get wishlist from Audible."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.audible.com/library/wishlist",
        "audible_wishlist",
    )
