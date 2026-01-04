from typing import Any

import zendriver as zd

from getgather.mcp.dpage import zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_actions import parse_response_json

traveloka_mcp = GatherMCP(brand_id="traveloka", name="Traveloka MCP")


@traveloka_mcp.tool
async def get_saved_list() -> dict[str, Any]:
    """Get the saved list from Traveloka"""

    async def action(tab: zd.Tab, _) -> dict[str, Any]:
        async with tab.expect_response(".*api/v2/ugc/bookmark/template/getList.*") as resp:
            await tab.get("https://www.traveloka.com/en-id/user/saved/list")
            raw_data = await parse_response_json(resp, [], "saved list")

        return {"traveloka_saved_list": raw_data}

    return await zen_dpage_with_action(
        "https://www.traveloka.com/en-id/user/saved/list",
        action,
    )
