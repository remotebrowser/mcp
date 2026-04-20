from typing import Any

import zendriver as zd
from loguru import logger

from getgather.browser import page_query_selector, zen_navigate_with_retry
from getgather.mcp.dpage import remote_zen_dpage_with_action
from getgather.mcp.registry import GatherMCP
from getgather.mcp.utils import retry_with_navigation
from getgather.zen_actions import parse_response_json

nordstrom_mcp = GatherMCP(brand_id="nordstrom", name="Nordstrom MCP")


async def get_order_details_with_retry(
    tab: zd.Tab, page_number: int = 1, max_retries: int = 3
) -> dict[str, Any]:
    """Get the details of an order from Nordstrom with retry logic"""
    logger.info(
        f"Starting get_order_details_with_retry (page_number={page_number}, max_retries={max_retries})"
    )

    async def fetch_orders() -> dict[str, Any]:
        await zen_navigate_with_retry(tab, "https://www.nordstrom.com/my-account")
        select_element = await page_query_selector(tab, "div > label > select", timeout=10)

        orders = None
        if select_element:
            async with tab.expect_response(".*/orders.*") as resp:
                logger.info("Response listener active. Triggering select_option('all')...")
                await select_element.select_option(value="all")
                orders = await parse_response_json(resp, {"orders": []}, "orders")
        else:
            logger.warning("Select element not found. Skipping dropdown selection.")

        if page_number > 1:
            logger.info(f"Looking for pagination link: ul li a[href='?page={page_number}']")
            pagination_link = await page_query_selector(
                tab, f"ul li a[href='?page={page_number}']", timeout=10
            )
            if not pagination_link:
                logger.warning(
                    f"Pagination link for page {page_number} not found. Returning empty orders."
                )
                return {"orders": []}

            logger.info(
                "Setting up response listener for pagination API response containing '/orders'..."
            )
            async with tab.expect_response(".*/orders.*") as resp:
                await pagination_link.click()
                orders = await parse_response_json(resp, {"orders": []}, "pagination orders")
        else:
            logger.info("Page 1 - no pagination needed")

        result = orders or {"orders": []}
        orders_count = (
            len(result.get("orders", [])) if isinstance(result.get("orders"), list) else 0
        )
        logger.info(f"Successfully retrieved orders. Returning {orders_count} orders.")
        return result

    return await retry_with_navigation(
        tab=tab,
        operation=fetch_orders,
        max_retries=max_retries,
        exceptions=(Exception,),
        re_raise_on_max_retries=True,
        operation_name=f"get_order_details_with_retry (page {page_number})",
    )


# Currently, no way for us to get the order detail based on the order id since
# the order id needs to be paired with lookupKey which is not available in the dom / ui
# so we need to listen specifically to the order details api call


@nordstrom_mcp.tool
async def get_order_history(page_number: int = 1) -> dict[str, Any]:
    """Get the details of an order from Nordstrom"""

    async def get_order_details_action(tab: zd.Tab, _) -> dict[str, Any]:
        """Get the details of an order from Nordstrom"""
        logger.info("🔧 Executing get_order_details_action...")
        result: dict[str, Any] = await get_order_details_with_retry(tab, page_number)
        result_keys: list[str] = list(result.keys())
        logger.info(f"✅ get_order_details_action completed. Result keys: {result_keys}")
        return result

    return await remote_zen_dpage_with_action(
        "https://www.nordstrom.com/my-account",
        get_order_details_action,
    )
