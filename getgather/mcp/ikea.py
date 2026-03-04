from typing import Any

from fastmcp import Context

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

ikea_mcp = GatherMCP(brand_id="ikea", name="Ikea MCP")


@ikea_mcp.tool
async def get_favorites(ctx: Context) -> dict[str, Any]:
    """Get the list of favorites from Ikea"""
    return await remote_zen_dpage_mcp_tool(
        "https://www.ikea.com/us/en/favorites/", "ikea_favorites"
    )
