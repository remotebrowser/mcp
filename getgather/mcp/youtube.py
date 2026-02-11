from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

youtube_mcp = GatherMCP(brand_id="youtube", name="YouTube MCP")


YOUTUBE_BASE = "https://www.youtube.com"


def _prepend_base_urls(result: dict[str, Any], key: str) -> dict[str, Any]:
    if "signin_id" in result:
        return result
    for entry in result.get(key, []):
        if "url" in entry and entry["url"].startswith("/"):
            entry["url"] = YOUTUBE_BASE + entry["url"]
    return result


@youtube_mcp.tool
async def get_liked_videos() -> dict[str, Any]:
    """Get liked videos from YouTube."""
    result = await zen_dpage_mcp_tool(
        "https://www.youtube.com/playlist?list=LL",
        "youtube_liked_videos",
    )
    return _prepend_base_urls(result, "youtube_liked_videos")


@youtube_mcp.tool
async def get_watch_history() -> dict[str, Any]:
    """Get watch history from YouTube."""
    result = await zen_dpage_mcp_tool(
        "https://www.youtube.com/feed/history",
        "youtube_watch_history",
    )
    return _prepend_base_urls(result, "youtube_watch_history")


@youtube_mcp.tool
async def get_channel_subscriptions() -> dict[str, Any]:
    """Get channel subscriptions from YouTube."""
    result = await zen_dpage_mcp_tool(
        YOUTUBE_BASE,
        "youtube_channel_subscriptions",
    )
    return _prepend_base_urls(result, "youtube_channel_subscriptions")
