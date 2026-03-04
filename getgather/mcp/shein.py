from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

shein_mcp = GatherMCP(brand_id="shein", name="Shein MCP")


@shein_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get orders from Shein."""
    return await remote_zen_dpage_mcp_tool("https://us.shein.com/user/orders/list", "shein_orders")
