from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

shadestore_mcp = GatherMCP(brand_id="shadestore", name="Shade Store MCP")


@shadestore_mcp.tool
async def get_carts() -> dict[str, Any]:
    """Get carts of the shade store."""
    return await zen_dpage_mcp_tool(
        f"https://www.theshadestore.com/cart", "shadestore_cart", timeout=60
    )
