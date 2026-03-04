from typing import Any

from fastmcp import Context

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

ashley_mcp = GatherMCP(brand_id="ashley", name="Ashley MCP")


@ashley_mcp.tool
async def get_cart(ctx: Context) -> dict[str, Any]:
    """Get the list of items in the cart from Ashley"""

    return await remote_zen_dpage_mcp_tool("https://www.ashleyfurniture.com/cart/", "ashley_cart")
