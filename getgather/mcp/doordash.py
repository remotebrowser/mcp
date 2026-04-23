from typing import Any, cast

import zendriver as zd
from loguru import logger

from getgather.browser import retry_with_navigation, zen_navigate_with_retry
from getgather.mcp.dpage import (
    remote_zen_dpage_mcp_tool,
    remote_zen_dpage_with_action,
)
from getgather.mcp.registry import GatherMCP

doordash_mcp = GatherMCP(brand_id="doordash", name="Doordash MCP")


@doordash_mcp.tool
async def get_orders() -> dict[str, Any]:
    """Get the orders from a user's Doordash account (local zen)."""
    return await remote_zen_dpage_mcp_tool("https://www.doordash.com/orders", "doordash_orders")


async def get_orders_from_api(tab: zd.Tab, page_number: int = 1) -> dict[str, Any]:
    """Get the orders from the Doordash API with retry logic"""
    logger.info(f"Starting get_orders_from_api (page_number={page_number})")

    async def fetch_orders() -> dict[str, Any]:
        orders = None

        await zen_navigate_with_retry(tab, "https://www.doordash.com/orders", wait_for_ready=False)
        offset = (page_number - 1) * 10
        orders = await tab.evaluate(
            f"""
                (async () => {{
                    const httpRequest = await new Promise(resolve => {{
                        const originalFetch = window.fetch;
                        window.fetch = async function (...args) {{
                            if(args[0].includes('/getConsumerOrdersWithDetails') && args[1].method === 'POST'){{
                                window.fetch = originalFetch;
                                resolve(args);
                            }}
                            const response = await originalFetch.apply(this, args);
                            return response;
                        }};
                    }})
                    
                    const url = httpRequest[0]
                    const headers = httpRequest[1].headers
                    const originalBody = JSON.parse(httpRequest[1].body);
                    const body = {{
                        ...originalBody,
                        variables: {{
                            ...originalBody.variables,
                            offset: {offset}
                        }}
                    }};
                    
                    const res = await fetch(url, {{
                        method: 'POST',
                        credentials: 'include',
                        headers,
                        body: JSON.stringify(body)
                    }});
                    if (!res.ok) {{
                        const error_text = await res.text();
                        throw new Error(`HTTP error! status: ${{res.status}} - ${{error_text}}`);
                    }}
                    return await res.json();
                }})()
            """,
            True,
        )
        return cast(dict[str, Any], orders)

    return await retry_with_navigation(
        tab=tab,
        operation=fetch_orders,
        max_retries=3,
        exceptions=(Exception,),
        re_raise_on_max_retries=True,
        timeout_seconds=30,
        operation_name=f"get_orders_from_api (page_number={page_number})",
    )


@doordash_mcp.tool
async def get_orders_with_pagination(page_number: int = 1) -> dict[str, Any]:
    """Get the order history from a user's Doordash account (remote zen)."""

    async def get_order_details_action(tab: zd.Tab, _) -> dict[str, Any]:
        """Get the details of an order from Doordash"""
        logger.info("🔧 Executing get_orders_from_api...")
        result: dict[str, Any] = await get_orders_from_api(tab, page_number)
        return {"doordash_orders": result.get("data", {}).get("getConsumerOrdersWithDetails", [])}

    return await remote_zen_dpage_with_action(
        "https://www.doordash.com/orders",
        get_order_details_action,
    )
