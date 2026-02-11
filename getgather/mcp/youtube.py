from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

youtube_mcp = GatherMCP(brand_id="youtube", name="YouTube MCP")


@youtube_mcp.tool
async def get_liked_videos() -> dict[str, Any]:
    """Get liked videos from YouTube."""
    return await zen_dpage_mcp_tool(
        "https://www.youtube.com/playlist?list=LL",
        "youtube_liked_videos",
    )


@youtube_mcp.tool
async def get_watch_history() -> dict[str, Any]:
    """Get watch history from YouTube."""
    return await zen_dpage_mcp_tool(
        "https://www.youtube.com/feed/history",
        "youtube_watch_history",
    )
