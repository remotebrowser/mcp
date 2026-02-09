import os
from typing import Any

import zendriver as zd

from getgather.mcp.dpage import zen_dpage_mcp_tool, zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_distill import (
    load_distillation_patterns,
    run_distillation_loop,
)

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

    async def action(page: zd.Tab, browser: zd.Browser) -> dict[str, Any]:
        path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
        patterns = load_distillation_patterns(path)
        terminated, _distilled, converted = await run_distillation_loop(
            "https://www.youtube.com/playlist?list=LL",
            patterns,
            browser,
            timeout=15,
            page=page,
            close_page=False,
        )
        if terminated:
            return {"youtube_liked_videos": converted if converted else []}
        raise ValueError("Failed to extract liked videos")

    return await zen_dpage_with_action(
        "https://www.youtube.com/playlist?list=LL",
        action,
        dpage_timeout=30,
    )
