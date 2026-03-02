from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool, zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

gofood_mcp = GatherMCP(brand_id="gofood", name="Gofood MCP")


@gofood_mcp.tool
async def get_purchase_history() -> dict[str, Any]:
    """Get gofood purchase history."""
    return await zen_dpage_mcp_tool("https://gofood.co.id/en/orders", "gofood_purchase_history")


@gofood_mcp.tool
async def remote_get_purchase_history() -> dict[str, Any]:
    """Get gofood purchase history."""
    return await remote_zen_dpage_mcp_tool(
        "https://gofood.co.id/en/orders", "gofood_purchase_history"
    )
