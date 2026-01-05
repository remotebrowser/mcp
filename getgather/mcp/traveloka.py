from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

traveloka_mcp = GatherMCP(brand_id="traveloka", name="Traveloka MCP")


@traveloka_mcp.tool
async def get_saved_list() -> dict[str, Any]:
    """Get the saved list from Traveloka"""
    return await zen_dpage_mcp_tool(
        "https://www.traveloka.com/en-id/user/saved/list",
        "traveloka_saved_list",
    )
