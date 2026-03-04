from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

bedbathandbeyond_mcp = GatherMCP(brand_id="bedbathandbeyond", name="Bed Bath and Beyond MCP")


@bedbathandbeyond_mcp.tool
async def get_favorites() -> dict[str, Any]:
    """Get favorites of bedbathandbeyond."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.bedbathandbeyond.com/profile/me/lists", "bedbathandbeyond_favorites"
    )
