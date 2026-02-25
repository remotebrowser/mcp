from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

doordash_mcp = GatherMCP(brand_id="doordash", name="Doordash MCP")


@doordash_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get the orders from a user's Doordash account."""
    return await remote_zen_dpage_mcp_tool("https://www.doordash.com/orders", "doordash_orders")
