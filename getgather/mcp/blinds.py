import asyncio
from typing import Any, cast

import zendriver as zd

from getgather.logs import logger
from getgather.mcp.dpage import zen_dpage_mcp_tool, zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_actions import parse_response_json
from getgather.zen_distill import ElementConfig, zen_navigate_with_retry

blinds_mcp = GatherMCP(brand_id="blinds", name="Blinds MCP")

# Element configuration for typing delays
blinds_config = ElementConfig(typing_clear_delay=0.5)


@blinds_mcp.tool
async def get_favorites() -> dict[str, Any]:
    """Get favorites of blinds."""
    return await zen_dpage_mcp_tool(
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


@blinds_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get orders of blinds."""

    async def get_orders_action(page: zd.Tab, browser: zd.Browser) -> dict[str, Any]:
        logger.info("🔧 Executing get_orders_action...")
        await zen_navigate_with_retry(
            page, "https://www.blinds.com/myaccount/orders", wait_for_ready=False
        )
        orders = None
        async with page.expect_response(".*/ordersummarylist") as resp:
            logger.info("Response listener active...")
            logger.info(f"Response: {resp}")
            orders = await parse_response_json(resp, [])

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

    return await zen_dpage_with_action(
        f"https://www.blinds.com/myaccount/orders",
        action=get_orders_action,
        dpage_timeout=60,
        config=blinds_config,
    )
