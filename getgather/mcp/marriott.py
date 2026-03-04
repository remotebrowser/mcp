from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

marriott_mcp = GatherMCP(brand_id="marriott", name="Marriott MCP")


@marriott_mcp.tool
async def get_profile() -> dict[str, Any]:
    """Get profile of Marriott."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.marriott.com/loyalty/myAccount/profile.mi", "marriott_profile"
    )
