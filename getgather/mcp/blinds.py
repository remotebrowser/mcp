import asyncio
from typing import Any, cast

import zendriver as zd
from loguru import logger

from getgather.browser import ElementConfig, retry_with_navigation, zen_navigate_with_retry
from getgather.mcp.dpage import (
    remote_zen_dpage_mcp_tool,
    remote_zen_dpage_with_action,
)
from getgather.mcp.registry import MCPTool
from getgather.zen_actions import parse_response_json

blinds_mcp = MCPTool(brand_id="blinds", name="Blinds MCP")

# Element configuration for typing delays
blinds_config = ElementConfig(typing_clear_delay=0.75)


@blinds_mcp.tool
async def get_favorites() -> dict[str, Any]:
    """Get favorites of blinds."""
    return await remote_zen_dpage_mcp_tool(
        f"https://www.blinds.com/myaccount/favorites",
        "blinds_favorites",
        timeout=60,
        config=blinds_config,
    )


async def get_order_details(page: zd.Tab, id: str) -> dict[str, Any]:
    """Get details of an order from blinds."""
    js_code = f"""
        (async () => {{
            const res = await fetch('https://www.blinds.com/api/myaccount/orders/orderdetails/{id}', {{
                method: 'GET',
                credentials: 'include',
            }});
            const json = await res.json();
            return json;
        }})()
    """
    result = await page.evaluate(js_code, True)
    return cast(dict[str, Any], result)


async def get_orders_action(page: zd.Tab, _: zd.Browser) -> dict[str, Any]:
    logger.info("🔧 Executing get_orders_action...")

    async def fetch_orders() -> list[dict[str, Any]]:
        # Set up response listener, then navigate to trigger the request
        # The response will be captured by the listener
        async with page.expect_response(".*/ordersummarylist") as resp:
            logger.info("Response listener active...")
            # Navigate to trigger the API call (response is triggered by page JavaScript)
            await zen_navigate_with_retry(
                page, "https://www.blinds.com/myaccount/orders", wait_for_ready=False
            )
            return await parse_response_json(resp, [])

    orders = await retry_with_navigation(
        tab=page,
        operation=fetch_orders,
        max_retries=3,
        timeout_seconds=5,
        exceptions=(asyncio.TimeoutError,),
        default_on_max_retries=[],
        operation_name="get_orders_action",
    )

    logger.info(f"🔍 Orders: {orders}")

    order_details_list = await asyncio.gather(
        *[get_order_details(page, order["orderNumber"]) for order in orders],
        return_exceptions=True,
    )

    for order, details in zip(orders, order_details_list):
        if isinstance(details, BaseException):
            logger.warning(
                f"Error getting order details for order {order['orderNumber']}: {details}"
            )
            continue
        order["details"] = details

    return {"blinds_orders": orders}


@blinds_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get orders of blinds."""
    return await remote_zen_dpage_with_action(
        f"https://www.blinds.com/myaccount/orders",
        action=get_orders_action,
        config=blinds_config,
    )
