from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

delta_mcp = GatherMCP(brand_id="delta", name="Delta MCP")


@delta_mcp.tool
async def get_trips() -> dict[str, Any]:
    """Get trips of delta."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.delta.com/my-trips/upcoming-trips", "delta_trips"
    )
