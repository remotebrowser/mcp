from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

ebay_mcp = GatherMCP(brand_id="ebay", name="Ebay MCP")


@ebay_mcp.tool
async def get_cart() -> dict[str, Any]:
    """Get the list of items in the cart from Ebay"""
    return await remote_zen_dpage_mcp_tool("https://cart.ebay.com/", "ebay_cart")
