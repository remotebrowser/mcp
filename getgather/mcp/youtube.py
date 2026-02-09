from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

youtube_mcp = GatherMCP(brand_id="youtube", name="YouTube MCP")


@youtube_mcp.tool
async def signin() -> dict[str, Any]:
    """Signin to YouTube."""
    return await zen_dpage_mcp_tool(
        "https://www.youtube.com",
        "signin",
    )


@youtube_mcp.tool
async def get_liked_videos() -> dict[str, Any]:
    """Get liked videos from YouTube."""
    return await zen_dpage_mcp_tool(
        "https://www.youtube.com/playlist?list=LL",
        "youtube_liked_videos",
    )
