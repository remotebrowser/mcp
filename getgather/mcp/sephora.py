from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

sephora_mcp = GatherMCP(brand_id="sephora", name="Sephora MCP")


@sephora_mcp.tool
async def get_cart() -> dict[str, Any]:
    """Get the list of items in the cart from Sephora"""
    return await remote_zen_dpage_mcp_tool("https://www.sephora.com/basket", "sephora_cart")
