from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

linkedin_mcp = GatherMCP(brand_id="linkedin", name="Linkedin MCP")


@linkedin_mcp.tool
async def get_feed() -> dict[str, Any]:
    """Get feed of Linkedin."""
    return await remote_zen_dpage_mcp_tool("https://www.linkedin.com/feed/", "linkedin_feed")
