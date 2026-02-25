from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

youtube_mcp = GatherMCP(brand_id="youtube", name="YouTube MCP")


YOUTUBE_BASE = "https://www.youtube.com"


def _prepend_base_urls(result: dict[str, Any], key: str) -> dict[str, Any]:
    if "signin_id" in result:
        return result
    value = result.get(key)
    if isinstance(value, str):
        return {key: []}
    for entry in result.get(key, []):
        for field in ("url", "channel_url"):
            if field in entry and entry[field].startswith("/"):
                entry[field] = YOUTUBE_BASE + entry[field]
    return result


@youtube_mcp.tool
async def get_liked_videos() -> dict[str, Any]:
    """Get liked videos from YouTube."""
    result = await remote_zen_dpage_mcp_tool(
        "https://www.youtube.com/playlist?list=LL",
        "youtube_liked_videos",
    )
    return _prepend_base_urls(result, "youtube_liked_videos")


@youtube_mcp.tool
async def get_watch_history() -> dict[str, Any]:
    """Get watch history from YouTube."""
    result = await remote_zen_dpage_mcp_tool(
        "https://www.youtube.com/feed/history",
        "youtube_watch_history",
    )
    return _prepend_base_urls(result, "youtube_watch_history")


@youtube_mcp.tool
async def get_watch_later() -> dict[str, Any]:
    """Get watch later playlist from YouTube."""
    result = await remote_zen_dpage_mcp_tool(
        "https://www.youtube.com/playlist?list=WL",
        "youtube_watch_later",
    )
    return _prepend_base_urls(result, "youtube_watch_later")


@youtube_mcp.tool
async def get_channel_subscriptions() -> dict[str, Any]:
    """Get channel subscriptions from YouTube."""
    result = await remote_zen_dpage_mcp_tool(
        "https://www.youtube.com/feed/subscriptions",
        "youtube_channel_subscriptions",
    )
    return _prepend_base_urls(result, "youtube_channel_subscriptions")
