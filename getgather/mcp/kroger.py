import asyncio
from typing import Any, cast

import zendriver as zd
from loguru import logger

from getgather.browser import safe_close_page
from getgather.mcp.dpage import (
    remote_zen_dpage_with_action,
)
from getgather.mcp.registry import MCPTool
from getgather.zen_actions import parse_response_json

kroger_mcp = MCPTool.registry["kroger"]


@kroger_mcp.tool
async def get_purchases(page_number: int = 1) -> dict[str, Any]:
    """Get the purchase history from a user's Kroger account via API."""

    async def get_purchases_action(page: zd.Tab, browser: zd.Browser) -> dict[str, Any]:
        logger.info(f"🔧 Executing get_purchase_history (page_number={page_number})...")

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
        result = cast(dict[str, Any], await page.evaluate(js_code, True))
        if result.get("errors", {}).get("statusCode") == 401:
            logger.info("User is not signed in")
            raise Exception("User is not signed in")

        purchases_raw = result.get("data", {}).get("postOrderSearch", {}).get("data", [])
        purchases: list[dict[str, Any]]
        if isinstance(purchases_raw, list):
            purchases_raw_list = cast(list[Any], purchases_raw)
            purchases = [item for item in purchases_raw_list if isinstance(item, dict)]
        else:
            purchases = []

        async def get_purchase_detail(receipt_key: str) -> dict[str, Any] | None:
            detail_tab = await browser.get("about:blank", new_tab=True)
            try:
                detail_url = f"https://www.kroger.com/mypurchases/detail/{receipt_key}"

                async def wait_for_detail_response() -> dict[str, Any]:
                    async with detail_tab.expect_response(
                        ".*purchase-history/v2/details.*"
                    ) as resp:
                        await detail_tab.get(detail_url)
                        purchase_detail = await parse_response_json(
                            resp,
                            {},
                            f"kroger purchase detail ({receipt_key})",
                        )
                        return purchase_detail

                return await asyncio.wait_for(wait_for_detail_response(), timeout=30)
            except asyncio.TimeoutError:
                logger.warning(
                    f"Timed out fetching purchase detail for receiptKey={receipt_key} "
                    f"(page_number={page_number})"
                )
                return None
            except Exception as e:
                logger.warning(
                    f"Error fetching purchase detail for receiptKey={receipt_key} "
                    f"(page_number={page_number}): {e}"
                )
                return None
            finally:
                await safe_close_page(detail_tab)

        receipt_keys: list[str] = []
        for purchase in purchases:
            receipt_key = purchase.get("receiptKey")
            if isinstance(receipt_key, str):
                receipt_keys.append(receipt_key)

        detail_results = await asyncio.gather(
            *[get_purchase_detail(receipt_key) for receipt_key in receipt_keys],
            return_exceptions=True,
        )

        purchase_details: list[dict[str, Any]] = []
        for receipt_key, detail_result in zip(receipt_keys, detail_results):
            if isinstance(detail_result, BaseException):
                logger.warning(
                    f"Unexpected error fetching purchase detail for receiptKey={receipt_key} "
                    f"(page_number={page_number}): {detail_result}"
                )
                continue
            if detail_result is not None:
                purchase_details.append(detail_result)

        return {
            "kroger_purchases": purchase_details,
        }

    return await remote_zen_dpage_with_action(
        "https://www.kroger.com/mypurchases",
        action=get_purchases_action,
    )
