from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

hilton_mcp = GatherMCP(brand_id="hilton", name="Hilton MCP")


@hilton_mcp.tool
async def get_activities() -> dict[str, Any]:
    """Get activities from Hilton."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.hilton.com/en/hilton-honors/guest/activity/", "hilton_activities"
    )
