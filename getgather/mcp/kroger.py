from typing import Any, cast

import zendriver as zd
from loguru import logger

from getgather.mcp.dpage import (
    remote_zen_dpage_mcp_tool,
    remote_zen_dpage_with_action,
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


async def get_purchase_history(page: zd.Tab, page_number: int = 1) -> dict[str, Any]:
    """Get purchase history from Kroger API."""
    url = f"https://www.kroger.com/atlas/v1/post-order/v1/purchase-history-search?pageNo={page_number}&pageSize=10"
    js_code = f"""
        (async function () {{
            const res = await fetch('{url}', {{
                method: 'GET',
                credentials: 'include',
            }});
            if (!res.ok) {{
                const error_text = await res.text();
                throw new Error("HTTP error! status: " + res.status?.toString() + " - " + error_text);
            }}
            return await res.json();
        }})()
    """
    result = await page.evaluate(js_code, True)
    return cast(dict[str, Any], result)


@kroger_mcp.tool
async def get_purchases_from_api(page_number: int = 1) -> dict[str, Any]:
    """Get the purchase history from a user's Kroger account via API."""

    async def get_purchases_action(page: zd.Tab, _: zd.Browser) -> dict[str, Any]:
        logger.info(f"🔧 Executing get_purchase_history (page_number={page_number})...")
        result = await get_purchase_history(page, page_number)
        return {"kroger_purchases": result}

    return await remote_zen_dpage_with_action(
        "https://www.kroger.com/mypurchases",
        action=get_purchases_action,
    )
