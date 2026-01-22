import asyncio
from typing import Any, cast

import zendriver as zd

from getgather.logs import logger
from getgather.mcp.dpage import zen_dpage_mcp_tool, zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_actions import parse_response_json
from getgather.zen_distill import zen_navigate_with_retry

shadestore_mcp = GatherMCP(brand_id="shadestore", name="Shade Store MCP")


@shadestore_mcp.tool
async def get_carts() -> dict[str, Any]:
    """Get carts of the shade store."""
    return await zen_dpage_mcp_tool(
        f"https://www.theshadestore.com/cart", "shadestore_cart", timeout=60
    )
