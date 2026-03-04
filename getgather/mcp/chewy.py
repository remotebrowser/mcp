from typing import Any

from fastmcp import Context

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

chewy_mcp = GatherMCP(brand_id="chewy", name="Chewy MCP")


@chewy_mcp.tool
async def get_orders(ctx: Context) -> dict[str, Any]:
    """Get the list of orders from Chewy"""
    return await remote_zen_dpage_mcp_tool(
        "https://www.chewy.com/app/account/orderhistory", "chewy_orders"
    )
