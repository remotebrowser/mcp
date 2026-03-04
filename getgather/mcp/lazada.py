from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

lazada_mcp = GatherMCP(brand_id="lazada", name="Lazada MCP")


@lazada_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get orders of lazada."""
    return await remote_zen_dpage_mcp_tool(
        "https://my.lazada.co.id/customer/order/index/",
        "lazada_orders",
    )
