from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

nike_mcp = GatherMCP(brand_id="nike", name="Nike MCP")


@nike_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get online orders of nike."""
    return await remote_zen_dpage_mcp_tool("https://www.nike.com/orders", "nike_orders")
