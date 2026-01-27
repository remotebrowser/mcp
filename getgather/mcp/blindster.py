import asyncio
from typing import Any, cast

import httpx
import zendriver as zd
from zendriver.core.connection import ProtocolException

from getgather.logs import logger
from getgather.mcp.dpage import zen_dpage_mcp_tool, zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.zen_actions import parse_response_json
from getgather.zen_distill import zen_navigate_with_retry

blindster_mcp = GatherMCP(brand_id="blindster", name="Blindster MCP")


@blindster_mcp.tool
async def get_carts() -> dict[str, Any]:
    """Get carts of blindster."""
    return await zen_dpage_mcp_tool(f"https://www.blindster.com/cart", "blindster_cart", timeout=60)


async def get_order_details(id: str, authorization_headers: str | None = None) -> dict[str, Any]:
    """Get details of an order from blindster."""
    url = f"https://api.blindster.com/ecommerce/customer/order/{id}"
    headers: dict[str, str] = {}
    if authorization_headers:
        headers["Authorization"] = authorization_headers
    logger.info(f"Getting order details for {id} with headers: {headers}")
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return cast(dict[str, Any], response.json())


@blindster_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get orders of blinds."""

    async def get_orders_action(page: zd.Tab, browser: zd.Browser) -> dict[str, Any]:
        logger.info("🔧 Executing get_orders_action...")

        max_retries = 3
        orders: list[dict[str, Any]] = []
        authorization_headers: str | None = None

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"get_orders_action attempt {attempt}/{max_retries}")
                await zen_navigate_with_retry(
                    page, "https://www.blindster.com/account/orders", wait_for_ready=False
                )

                async with page.expect_response(".*/ecommerce/customer/orders") as resp:
                    logger.info("Response listener active...")
                    request_value = await resp.request
                    request_headers = cast(dict[str, str], request_value.headers)
                    authorization_headers = request_headers.get(
                        "authorization"
                    ) or request_headers.get("Authorization")
                    orders = await parse_response_json(resp, [])

                logger.info("Orders successfully retrieved from Blindster.")
                break

            except ProtocolException as e:
                logger.error(
                    f"get_orders_action attempt {attempt}/{max_retries} failed with "
                    f"ProtocolException while fetching orders: {e}"
                )
                if attempt == max_retries:
                    logger.error("Max retries reached for get_orders_action; re-raising error.")
                    raise
                logger.info("Retrying get_orders_action...")

        order_details_list = await asyncio.gather(
            *[get_order_details(order["orderNumber"], authorization_headers) for order in orders],
            return_exceptions=True,
        )

        for order, details in zip(orders, order_details_list):
            if isinstance(details, BaseException):
                logger.warning(
                    f"Error getting order details for order {order['orderNumber']}: {details}"
                )
                continue
            order["details"] = details

        return {"blindster_orders": orders}

    return await zen_dpage_with_action(
        f"https://www.blindster.com/account/orders",
        action=get_orders_action,
        dpage_timeout=60,
    )
