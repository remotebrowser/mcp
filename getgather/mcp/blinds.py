from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

blinds_mcp = GatherMCP(brand_id="blinds", name="Blinds MCP")


@blinds_mcp.tool
async def get_favorites() -> dict[str, Any]:
    """Get favorites of blinds."""
    return await zen_dpage_mcp_tool(
        f"https://www.blinds.com/myaccount/favorites", "blinds_favorites", timeout=60
    )
