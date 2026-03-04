from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

starbucks_mcp = GatherMCP(brand_id="starbucks", name="Starbucks MCP")


@starbucks_mcp.tool
async def get_my_rewards() -> dict[str, Any]:
    """Get my rewards of Starbucks."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.starbucks.com/account/rewards", "starbucks_my_rewards", timeout=10
    )
