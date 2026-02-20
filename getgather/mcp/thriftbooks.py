from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

thriftbooks_mcp = GatherMCP(brand_id="thriftbooks", name="Thriftbooks MCP")


@thriftbooks_mcp.tool
async def get_order_history() -> dict[str, Any]:
    """Get order history of thriftbooks."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.thriftbooks.com/account/ordersummary/", "thriftbooks_order_history"
    )
