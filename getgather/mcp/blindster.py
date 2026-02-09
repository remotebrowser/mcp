import asyncio
from typing import Any, cast

import httpx
import zendriver as zd
from zendriver.core.connection import ProtocolException

from getgather.logs import logger
from getgather.mcp.dpage import zen_dpage_mcp_tool, zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.mcp.utils import retry_with_navigation
from getgather.zen_actions import parse_response_json

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

        orders: list[dict[str, Any]] = []
        authorization_headers: str | None = None

        async def fetch_orders() -> tuple[list[dict[str, Any]], str | None]:
            async with page.expect_response(".*/ecommerce/customer/orders") as resp:
                logger.info("Response listener active...")
                request_value = await resp.request
                request_headers = cast(dict[str, str], request_value.headers)
                auth_headers = request_headers.get("authorization") or request_headers.get(
                    "Authorization"
                )
                orders_data = await parse_response_json(resp, [])
                return orders_data, auth_headers

        orders, authorization_headers = await retry_with_navigation(
            tab=page,
            operation=fetch_orders,
            navigation_url="https://www.blindster.com/account/orders",
            max_retries=3,
            exceptions=(ProtocolException,),
            re_raise_on_max_retries=True,
            operation_name="get_orders_action",
        )

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
