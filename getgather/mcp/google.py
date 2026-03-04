from typing import Any

from fastmcp import Context

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

google_mcp = GatherMCP(brand_id="google", name="Google MCP")


@google_mcp.tool
async def get_activity(ctx: Context) -> dict[str, Any]:
    """Get the list of activity from Google"""

    return await remote_zen_dpage_mcp_tool("https://myactivity.google.com/myactivity", "google_activity")
