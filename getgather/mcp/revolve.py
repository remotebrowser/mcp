from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

revolve_mcp = GatherMCP(brand_id="revolve", name="Revolve MCP")


@revolve_mcp.tool
async def get_carts() -> dict[str, Any]:
    """Get carts items from Revolve."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.revolve.com/r/ShoppingBag.jsp", "revolve_cart"
    )
