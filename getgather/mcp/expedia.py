from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

expedia_mcp = GatherMCP(brand_id="expedia", name="Expedia MCP")


@expedia_mcp.tool
async def get_past_trips() -> dict[str, Any]:
    """Get past trips from Expedia."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.expedia.com/trips/list/3", "expedia_past_trips", timeout=10
    )
