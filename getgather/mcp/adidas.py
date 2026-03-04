from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

adidas_mcp = GatherMCP(brand_id="adidas", name="Adidas MCP")


@adidas_mcp.tool
async def get_order_history() -> dict[str, Any]:
    """Get order history of a adidas."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.adidas.com/us/my-account/order-history", "adidas_order_history"
    )
