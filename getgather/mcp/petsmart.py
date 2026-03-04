from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

petsmart_mcp = GatherMCP(brand_id="petsmart", name="Petsmart MCP")


@petsmart_mcp.tool
async def get_cart() -> dict[str, Any]:
    """Get the list of items in the cart from Petsmart"""
    return await remote_zen_dpage_mcp_tool(
        "https://www.petsmart.com/cart/", "petsmart_cart", timeout=5
    )
