from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

seatgeek_mcp = GatherMCP(brand_id="seatgeek", name="SeatGeek MCP")


@seatgeek_mcp.tool
async def get_tickets() -> dict[str, Any]:
    """Get tickets of seatgeek."""
    return await remote_zen_dpage_mcp_tool(
        "https://seatgeek.com/account/tickets", "seatgeek_tickets"
    )
