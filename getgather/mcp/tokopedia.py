import asyncio
import json
from typing import Any, Literal
from urllib.parse import quote, urlparse

import zendriver as zd
from loguru import logger

from getgather.browser import page_query_selector, retry_with_navigation, zen_navigate_with_retry
from getgather.mcp.dpage import (
    remote_zen_dpage_mcp_tool,
    remote_zen_dpage_with_action,
)
from getgather.mcp.registry import GatherMCP
from getgather.zen_actions import parse_response_json

tokopedia_mcp = GatherMCP(brand_id="tokopedia", name="Tokopedia MCP")


@tokopedia_mcp.tool
async def search_product(
    keyword: str | list[str],
    page_number: int = 1,
) -> dict[str, Any]:
    """Search products on Tokopedia."""
    keywords = [keyword] if isinstance(keyword, str) else keyword

    async def search_single_product(kw: str) -> dict[str, Any]:
        encoded_keyword = quote(kw)
        url = f"https://www.tokopedia.com/search?q={encoded_keyword}&page={page_number}"
        result = await remote_zen_dpage_mcp_tool(
            initial_url=url,
            result_key="product_list",
        )
        return {kw: result.get("product_list", result)}

    results_list = await asyncio.gather(*[search_single_product(kw) for kw in keywords])

    merged_results: dict[str, Any] = {}
    for r in results_list:
        merged_results.update(r)

    return {"product_list": merged_results}


@tokopedia_mcp.tool
async def get_product_details(product_url: str) -> dict[str, Any]:
    """Get product details from tokopedia. Get product_url from search_product tool."""
    return await remote_zen_dpage_mcp_tool(
        initial_url=product_url,
        result_key="product_detail",
        timeout=10,
    )


@tokopedia_mcp.tool
async def search_shop(keyword: str) -> dict[str, Any]:
    """Search shop on tokopedia."""
    encoded_keyword = quote(keyword)
    url = f"https://www.tokopedia.com/search?st=shop&q={encoded_keyword}"
    return await remote_zen_dpage_mcp_tool(
        initial_url=url,
        result_key="shop_list",
    )


@tokopedia_mcp.tool
async def get_shop_details(
    product_url: str | None = None,
    shop_url: str | None = None,
) -> dict[str, Any]:
    """Get store details from tokopedia by product_url or shop_url. Get product_url from search_product tool or shop_url from search_shop tool.
    If both are provided, shop_url takes precedence."""
    if not product_url and not shop_url:
        return {"error": "Either product_url or shop_url must be provided"}

    target_url = None
    if shop_url:
        try:
            parsed_shop = urlparse(shop_url)
            if not all([parsed_shop.scheme, parsed_shop.netloc]):
                return {"error": "Invalid shop URL - missing scheme or domain"}
            if not parsed_shop.netloc.endswith("tokopedia.com"):
                return {"error": "Invalid shop URL - must be a tokopedia.com domain"}
            target_url = shop_url
        except Exception:
            return {"error": "Invalid shop URL format"}

    if not target_url and product_url:
        try:
            parsed = urlparse(product_url)
            if not all([parsed.scheme, parsed.netloc]):
                return {"error": "Invalid product URL - missing scheme or domain"}
            if not parsed.netloc.endswith("tokopedia.com"):
                return {"error": "Invalid product URL - must be a tokopedia.com domain"}

            path_parts = [part for part in parsed.path.split("/") if part]
            if not path_parts:
                return {
                    "error": "Invalid product URL - cannot derive shop URL from root or empty path"
                }

            shop_segment = path_parts[0]
            if not shop_segment:
                return {"error": "Invalid product URL - cannot derive shop name from URL"}

            target_url = f"{parsed.scheme}://{parsed.netloc}/{shop_segment}"
        except Exception:
            return {"error": "Invalid product URL format"}

    if not target_url:
        return {"error": "Could not determine valid shop URL"}

    return await remote_zen_dpage_mcp_tool(
        initial_url=target_url,
        result_key="shop_detail",
    )


@tokopedia_mcp.tool
async def get_purchase_history(
    *,
    page_number: int = 1,
) -> dict[str, Any]:
    """Get purchase history of a tokopedia."""

    async def action(tab: zd.Tab, _: Any) -> dict[str, Any]:
        results: list[dict[str, Any]] = []

        async def fetch_purchase_history() -> list[dict[str, Any]] | None:
            async with tab.expect_response(".*gql.tokopedia.com/graphql/GetOrderHistory.*") as resp:
                await tab.get(f"https://www.tokopedia.com/order-list?page={page_number}")
                return await parse_response_json(resp, [], "purchase history")

        raw_data = await retry_with_navigation(
            tab=tab,
            operation=fetch_purchase_history,
            max_retries=3,
            exceptions=(Exception,),
            timeout_seconds=10,
            default_on_max_retries=None,
            operation_name="get_purchase_history",
        )

        if raw_data:
            uoh_orders: dict[str, Any] = raw_data[0].get("data", {}).get("uohOrders", {})
            orders: list[dict[str, Any]] = uoh_orders.get("orders", [])
            for order in orders:
                metadata: dict[str, Any] = order.get("metadata", {})
                shop: dict[str, Any] = json.loads(metadata.get("queryParams", "{}"))
                list_product_str = order.get("metadata", {}).get("listProducts", "[]")

                product_results: list[dict[str, Any]] = order.get("metadata", {}).get(
                    "products", []
                )
                if list_product_str != "" and product_results == []:
                    product_results = []
                    products: list[dict[str, Any]] = json.loads(list_product_str)
                    for product in products:
                        product_result = {
                            "title": product.get("product_name", ""),
                            "product_price": product.get("product_price", ""),
                            "original_price": product.get("original_price", ""),
                            "quantity": product.get("quantity", ""),
                            "imageURL": "",
                        }
                        product_results.append(product_result)
                result = {
                    "shop_name": shop.get("shop_name", ""),
                    "products": product_results,
                    "purchase_detail_url": f"https://www.tokopedia.com{metadata.get('detailURL', {}).get('webURL')}",
                    "payment_date": metadata.get("paymentDate", ""),
                    "status": metadata.get("status", {}).get("label", ""),
                    "total_price": metadata.get("totalPrice", {}).get("value", ""),
                }
                results.append(result)

        return {"purchase_history": results, "page": page_number}

    return await remote_zen_dpage_with_action(
        "https://www.tokopedia.com/order-list",
        action,
    )


@tokopedia_mcp.tool
async def get_cart() -> dict[str, Any]:
    """Get cart of a tokopedia."""

    async def action(tab: zd.Tab, _: Any) -> dict[str, Any]:
        results: list[dict[str, Any]] = []

        async with tab.expect_response(".*gql.tokopedia.com/graphql/cart_revamp_v4.*") as resp:
            await zen_navigate_with_retry(tab, "https://www.tokopedia.com/cart")
            raw_data = await parse_response_json(resp, [], "cart")

        if raw_data:
            carts: list[dict[str, Any]] = (
                raw_data[0]
                .get("data", {})
                .get("cart_revamp_v4", {})
                .get("data", {})
                .get("available_section", {})
                .get("available_group", [])
            )
            for cart in carts:
                products: list[dict[str, Any]] = []
                for shop_cart in cart.get("group_shop_v2_cart", []):
                    for shop_cart_detail in shop_cart.get("cart_details", []):
                        for product in shop_cart_detail.get("products", []):
                            products.append({
                                "product_id": product.get("product_id", ""),
                                "product_name": product.get("product_name", ""),
                                "product_price": product.get("product_price", ""),
                                "product_original_price": product.get("product_original_price", ""),
                                "product_url": product.get("product_url", ""),
                                "product_quantity": product.get("product_quantity", ""),
                                "discount_percentage": product.get("slash_price_label", ""),
                                "checked": product.get("checkbox_state", ""),
                            })
                result = {
                    "shop_name": cart.get("group_information", {}).get("name", ""),
                    "products": products,
                }
                results.append(result)

        total_price_element = await page_query_selector(
            tab, "div[data-testid='cartSummaryTotalPrice']", timeout=5
        )
        total_price = await total_price_element.inner_html() if total_price_element else ""

        return {"cart": results, "total_price": total_price}

    return await remote_zen_dpage_with_action(
        "https://www.tokopedia.com/cart",
        action,
    )


@tokopedia_mcp.tool
async def get_wishlist(page_number: int = 1) -> dict[str, Any]:
    """Get wishlist from tokopedia."""

    async def action(tab: zd.Tab, _: Any) -> dict[str, Any]:
        results: list[dict[str, Any]] = []

        async with tab.expect_response(
            ".*gql.tokopedia.com/graphql/GetWishlistCollectionItems.*"
        ) as resp:
            await tab.get(f"https://www.tokopedia.com/wishlist/all?page={page_number}")
            raw_data = await parse_response_json(resp, [], "wishlist")

        if raw_data:
            wishlist_data: dict[str, Any] = (
                raw_data[0].get("data", {}).get("get_wishlist_collection_items", {})
            )
            wishlists: list[dict[str, Any]] = wishlist_data.get("items", [])
            for wishlist in wishlists:
                result = {
                    "product_name": wishlist.get("name", ""),
                    "available": wishlist.get("available", ""),
                    "label_stock": wishlist.get("label_stock", ""),
                    "min_order": wishlist.get("min_order", ""),
                    "original_price": wishlist.get("original_price", ""),
                    "price": wishlist.get("price", ""),
                    "sold_count": wishlist.get("sold_count", ""),
                    "shop_name": wishlist.get("shop", {}).get("name", ""),
                }
                results.append(result)

        return {"wishlist": results}

    return await remote_zen_dpage_with_action("https://www.tokopedia.com/wishlist/all", action)


@tokopedia_mcp.tool
async def remote_action_product_in_cart(
    product_id: str | list[str],
    action: Literal["toggle_checklist", "remove_from_cart"],
) -> dict[str, Any]:
    """Action a product in cart of a tokopedia. Receive product_id from get_cart tool. After this tool, you need to call get_cart tool to get the updated cart.
    Action can be toggle_checklist or remove_from_cart."""

    logger.info(f"Actioning product in cart: {product_id} with action: {action}")

    product_ids = [product_id] if isinstance(product_id, str) else product_id

    async def perform_action(tab: zd.Tab, _: Any) -> dict[str, Any]:
        results_list: list[dict[str, str]] = []
        for pid in product_ids:
            if action == "toggle_checklist":
                selector = f"div[data-testid='productInfoAvailable-{pid}'] span[data-testid='CartListShopProductBox']"
            else:
                selector = f"div[data-testid='productInfoAvailable-{pid}'] button:has(svg[data-testid='cartBtnDelete'])"

            await asyncio.sleep(1)
            element = await page_query_selector(tab, selector, timeout=10)
            if element:
                await element.click()
            await asyncio.sleep(1)
            results_list.append({"message": f"Product {action}ed in cart", "product_id": pid})

        return {"results": results_list}

    return await remote_zen_dpage_with_action(
        "https://www.tokopedia.com/cart",
        perform_action,
    )
