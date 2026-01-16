from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

netflix_mcp = GatherMCP(brand_id="netflix", name="Netflix MCP")


@netflix_mcp.tool
async def get_viewing_activity() -> dict[str, Any]:
    """Get viewing activity of Netflix."""
    return await zen_dpage_mcp_tool(
        "https://www.netflix.com/viewingactivity", "netflix_viewing_activity", timeout=10
    )
