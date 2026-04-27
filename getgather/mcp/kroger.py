from typing import Any

from getgather.mcp.dpage import (
    remote_zen_dpage_mcp_tool,
)
from getgather.mcp.registry import MCPTool

kroger_mcp = MCPTool.registry["kroger"]


@kroger_mcp.tool
async def get_purchases() -> dict[str, Any]:
    """Get purchases from a user Kroger account."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.kroger.com/mypurchases",
        "kroger_get_purchases",
    )
