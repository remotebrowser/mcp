import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, cast

from patchright.async_api import Page, Response

from getgather.browser.profile import BrowserProfile
from getgather.distill import convert, load_distillation_patterns, run_distillation_loop
from getgather.logs import logger
from getgather.mcp.dpage import dpage_mcp_tool, dpage_with_action
from getgather.mcp.registry import GatherMCP

amazon_mcp = GatherMCP(brand_id="amazon", name="Amazon MCP")


def normalize_order_id(order_id: str | list[str] | None) -> str | list[str] | None:
    # Normalize order IDs (e.g. turn 'Order #114-3381700-2661062' into '114-3381700-2661062')
    if order_id is None:
        return order_id
    if isinstance(order_id, list):
        return order_id
    if order_id.startswith("Order #"):
        return order_id.replace("Order #", "").strip()
    return order_id


@amazon_mcp.tool
async def search_purchase_history(keyword: str, page_number: int = 1) -> dict[str, Any]:
    """Search purchase history from amazon."""
    return await dpage_mcp_tool(
        f"https://www.amazon.com/your-orders/search?page={page_number}&search={keyword}",
        "order_history",
    )


@amazon_mcp.tool
async def search_product(keyword: str) -> dict[str, Any]:
    """Search product on amazon."""
    return await dpage_mcp_tool(
        f"https://www.amazon.com/s?k={keyword}",
        "product_list",
    )


@amazon_mcp.tool
async def get_browsing_history() -> dict[str, Any]:
    """Get browsing history from amazon."""

    async def get_browsing_history_action(page: Page, _) -> dict[str, Any]:
        current_url = page.url
        if "signin" in current_url:
            raise Exception("User is not signed in")

        await page.wait_for_load_state("domcontentloaded")
        is_empty = await page.locator(
            "span:has-text('You have no recently viewed items.')"
        ).is_visible()
        if is_empty:
            return {"browsing_history_data": []}

        await page.goto(
            "https://www.amazon.com/gp/history?ref_=nav_AccountFlyout_browsinghistory",
            wait_until="commit",
        )

        def _url_matches(resp: Response) -> bool:
            """Predicate that checks if the response URL contains the predicate string."""

            return "browsing-history/" in resp.url

        response: Response = cast(
            Response,
            await page.wait_for_event(  # type: ignore[reportUnknownReturnType]
                "response",
                _url_matches,
                timeout=90_000,
            ),
        )

        browsing_history_url = response.url

        raw_attribute = await page.locator("div[data-client-recs-list]").get_attribute(
            "data-client-recs-list"
        )
        output = [json.dumps(item) for item in json.loads(raw_attribute or "[]")]

        async def get_browsing_history(start_index: int, end_index: int):
            logger.info(f"Getting browsing history from {start_index} to {end_index}")
            re = await page.request.post(
                url=browsing_history_url,
                data=json.dumps({"ids": output[start_index:end_index]}),
                headers=response.request.headers,
            )
            html = await re.text()
            distilled = f"""
                <html gg-domain="amazon">
                    <body>
                        {html}
                    </body>
                    <script type="application/json" id="browsing_history">
                        {{
                            "rows": "div#gridItemRoot",
                            "columns": [
                                {{
                                    "name": "name",
                                    "selector": "a.a-link-normal > span > div"
                                }},
                                {{
                                    "name": "url",
                                    "selector": "div[class*='uncoverable-faceout'] > a[class='a-link-normal aok-block']",
                                    "attribute": "href"
                                }},
                                {{
                                    "name": "image_url",
                                    "selector": "a > div > img.a-dynamic-image",
                                    "attribute": "src"
                                }},
                                {{
                                    "name": "rating",
                                    "selector": "div.a-icon-row > a > i > span"
                                }},
                                {{
                                    "name": "rating_count",
                                    "selector": "div.a-icon-row > a > span"
                                }},
                                {{
                                    "name": "price",
                                    "selector": "span.a-color-price > span"
                                }},
                                {{
                                    "name": "price_unit",
                                    "selector": "span[class='a-size-mini a-color-price aok-nowrap']"
                                }},
                                {{
                                    "name": "delivery_message",
                                    "selector": "div.udm-primary-delivery-message"
                                }}
                            ]
                        }}
                    </script>
                </html>
            """
            converted = await convert(distilled)
            if converted is not None:
                for item in converted:
                    item["url"] = f"https://www.amazon.com{item['url']}"
            return converted

        browsing_history_list = await asyncio.gather(*[
            get_browsing_history(i, i + 100) for i in range(0, len(output), 100)
        ])

        return {"browsing_history_data": browsing_history_list}

    return await dpage_with_action(
        "https://www.amazon.com/gp/history?ref_=nav_AccountFlyout_browsinghistory",
        action=get_browsing_history_action,
    )


async def get_purchase_with_details(page: Page, year: int, start_index: int) -> Any:
    html = await page.evaluate(f"""
        async () => {{
            const res = await fetch('https://www.amazon.com/gp/css/order-history?disableCsd=no-js&ref_=nav_AccountFlyout_orders&timeFilter=year-{year}&startIndex={start_index}', {{
                method: 'GET',
                credentials: 'include',
            }});
            const text = await res.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(text, 'text/html');

            const el = doc.querySelector("div.your-orders-content-container__content");
            return el ? el.innerHTML : null;
        }}
    """)

    distilled = f"""
        <html gg-domain="amazon">
            <body>
                {html}
            </body>
            <script type="application/json" id="orders">
                {{
                    "rows": "div.order-card.js-order-card",
                    "columns": [
                        {{
                            "name": "order_date",
                            "selector": "div.a-box-inner h5 div.a-span3 div:nth-child(2), div.a-box-inner div.a-span3 div:nth-child(2)"
                        }},
                        {{
                            "name": "order_total",
                            "selector": "div.a-box-inner h5 div.a-span2 div:nth-child(2), div.a-box-inner div.a-span2 div:nth-child(2)"
                        }},
                        {{
                            "name": "ship_to",
                            "selector": "div.yohtmlc-recipient div:nth-child(2) div.a-popover-preload"
                        }},
                        {{
                            "name": "order_id",
                            "selector": "div.yohtmlc-order-id span:nth-child(2)"
                        }},
                        {{
                            "name": "product_names",
                            "selector": "div.yohtmlc-product-title a",
                            "kind": "list"
                        }},
                        {{
                            "name": "image_urls",
                            "selector": "div.product-image img, .item-view-left-col-inner img",
                            "attribute": "src",
                            "kind": "list"
                        }},
                        {{
                            "name": "product_urls",
                            "selector": "div.yohtmlc-product-title a",
                            "attribute": "href",
                            "kind": "list"
                        }},
                        {{
                            "name": "return_window_dates",
                            "selector": "span[class='a-size-small']",
                            "kind": "list"
                        }},
                        {{
                            "name": "product_type",
                            "selector": "span.a-size-small.a-color-secondary.a-text-bold, .a-size-small.a-color-secondary.a-text-bold",
                            "kind": "list"
                        }},
                        {{
                            "name": "author_or_creator",
                            "selector": "span.a-size-small:not(.a-color-secondary), .a-size-small:not(.a-color-secondary)",
                            "kind": "list"
                        }},
                        {{
                            "name": "shipment_status",
                            "selector": "span.a-size-medium.delivery-box__primary-text, .yohtmlc-shipment-status-primaryText span"
                        }},
                        {{
                            "name": "store_logo",
                            "selector": "div.brand-logo img",
                            "attribute": "alt"
                        }}
                    ]
                }}
            </script>
        </html>
    """
    orders = await convert(distilled)

    return orders


@amazon_mcp.tool
async def get_purchase_history_yearly(year: str | int | None = None) -> dict[str, Any]:
    """Get purchase/order history of a amazon with dpage."""

    if year is None:
        target_year = datetime.now().year
    elif isinstance(year, str):
        try:
            target_year = int(year)
        except ValueError:
            target_year = datetime.now().year
    else:
        target_year = int(year)

    current_year = datetime.now().year
    if not (1900 <= target_year <= current_year + 1):
        raise ValueError(f"Year {target_year} is out of valid range (1900-{current_year + 1})")

    async def get_order_details_action(
        page: Page, browser_profile: BrowserProfile
    ) -> dict[str, Any]:
        current_url = page.url
        if "signin" in current_url:
            raise Exception("User is not signed in")

        start_index = 0

        orders: Any = []
        hasItem = True
        while hasItem:
            order_with_details = await get_purchase_with_details(page, target_year, start_index)
            if order_with_details is None:
                break
            orders.extend(order_with_details)
            start_index += 10
            if len(order_with_details) < 10:
                hasItem = False

        async def get_order_details(order: dict[str, Any]):
            order_id = order["order_id"]
            store_logo = order.get("store_logo")
            # If we already have product prices, return early
            product_prices = order.get("product_prices")
            if isinstance(product_prices, list):
                return {"order_id": order_id}

            # Determine order type based on brand logo alt text
            order_type = "regular"
            if store_logo:
                store_logo_text = str(store_logo).lower()
                if "whole foods" in store_logo_text:
                    order_type = "wholefoods"
                elif "fresh" in store_logo_text:
                    order_type = "fresh"

            match order_type:
                case "wholefoods":
                    # Use Whole Foods URL format
                    url = f"https://www.amazon.com/fopo/order-details?orderID={order_id}&ref=ppx_yo2ov_dt_b_fed_wwgs_wfm_ATVPDKIKX0DER&page=itemmod"
                    result = await page.evaluate(f"""
                        async () => {{
                            const res = await fetch('{url}', {{
                                method: 'GET',
                                credentials: 'include',
                            }});
                            const text = await res.text();
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(text, 'text/html');
                            doc.querySelectorAll('script').forEach(s => s.remove());

                            const itemRows = doc.querySelectorAll('div.a-row.a-spacing-base');
                            const prices = [];
                            const productNames = [];
                            const productUrls = [];
                            const imageUrls = [];

                            itemRows.forEach(row => {{
                                const productLink = row.querySelector('div.a-column.a-span10 > a.a-size-small.a-link-normal');
                                if (productLink) {{
                                    const name = productLink.textContent?.trim();
                                    if (name) {{
                                        productNames.push(name);
                                    }}
                                    const href = productLink.getAttribute('href');
                                    if (href) {{
                                        productUrls.push(href);
                                    }}
                                }}

                                const priceSpan = row.querySelector('div.a-column.a-span2.a-span-last div.a-text-right span.a-size-small');
                                if (priceSpan) {{
                                    prices.push(priceSpan.textContent?.trim() || '');
                                }}

                                const img = row.querySelector('img.ufpo-itemListWidget-image');
                                if (img) {{
                                    const src = img.getAttribute('src') || img.getAttribute('data-a-hires');
                                    if (src) {{
                                        imageUrls.push(src);
                                    }}
                                }}
                            }});

                            return {{
                                prices,
                                productNames,
                                productUrls,
                                imageUrls
                            }};
                        }}
                    """)
                    return {"order_id": order_id, **result}

                case "fresh":
                    # Use Fresh URL format
                    url = f"https://www.amazon.com/uff/your-account/order-details?orderID={order_id}&ref=ppx_yo2ov_dt_b_fed_wwgs_yo_odp_A1VC38T7YXB528&page=itemmod"
                    result = await page.evaluate(f"""
                        async () => {{
                            const res = await fetch('{url}', {{
                                method: 'GET',
                                credentials: 'include',
                            }});
                            const text = await res.text();
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(text, 'text/html');
                            doc.querySelectorAll('script').forEach(s => s.remove());

                            const itemRows = doc.querySelectorAll('div[id$="-item-grid-row"]');
                            const prices = [];
                            const productNames = [];
                            const productUrls = [];
                            const imageUrls = [];

                            itemRows.forEach(row => {{
                                const priceSpan = row.querySelector('span[id$="-item-total-price"]');
                                if (priceSpan) {{
                                    prices.push(priceSpan.textContent?.trim() || '');
                                }}

                                const productLink = row.querySelector('a.a-link-normal.a-text-normal');
                                if (productLink) {{
                                    const nameSpan = productLink.querySelector('span');
                                    if (nameSpan) {{
                                        const name = nameSpan.textContent?.trim();
                                        if (name) {{
                                            productNames.push(name);
                                        }}
                                    }}
                                    const href = productLink.getAttribute('href');
                                    if (href) {{
                                        productUrls.push(href);
                                    }}
                                }}

                                const img = row.querySelector('div.ufpo-item-image-column img');
                                if (img) {{
                                    const src = img.getAttribute('src') || img.getAttribute('data-a-hires');
                                    if (src) {{
                                        imageUrls.push(src);
                                    }}
                                }}
                            }});

                            return {{
                                prices,
                                productNames,
                                productUrls,
                                imageUrls
                            }};
                        }}
                    """)
                    return {"order_id": order_id, **result}

                case _:
                    # Use regular order URL format
                    url = f"https://www.amazon.com/gp/css/summary/print.html?orderID={order_id}&ref=ppx_yo2ov_dt_b_fed_invoice_pos"
                    prices = await page.evaluate(f"""
                        async () => {{
                            const res = await fetch('{url}', {{
                                method: 'GET',
                                credentials: 'include',
                            }});
                            const text = await res.text();
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(text, 'text/html');
                            doc.querySelectorAll('script').forEach(s => s.remove());

                            const rows = doc.querySelectorAll("div.a-fixed-left-grid");
                            const prices = Array.from(rows)
                                .map(row => row.querySelector("span.a-price span.a-offscreen")?.textContent?.trim())
                                .filter(Boolean);
                            return prices;
                        }}
                    """)
                    return {"order_id": order_id, "prices": prices}

        for order in orders:
            order["order_id"] = normalize_order_id(order.get("order_id")) or ""
        try:
            order_details_list = await asyncio.gather(
                *[get_order_details(order) for order in orders], return_exceptions=True
            )

            for i, item in enumerate(order_details_list):
                if isinstance(item, BaseException):
                    order_id = orders[i]["order_id"]
                    logger.warning(f"Error getting order details for order: {order_id}: {item}")

            order_details = {
                item["order_id"]: item
                for item in order_details_list
                if not isinstance(item, BaseException)
            }
            for order in orders:
                details = order_details.get(order["order_id"])
                if details is None:
                    continue
                if details.get("prices") is not None:
                    order["product_prices"] = details["prices"]
                # For Fresh/Whole Foods orders, replace product information with the complete details
                if order.get("store_logo") and details.get("productNames"):
                    order["product_names"] = details["productNames"]
                    order["product_urls"] = details["productUrls"]
                    order["image_urls"] = details["imageUrls"]
        except Exception as e:
            logger.error(f"Error getting order details for order: {e}")
            pass
        return {"amazon_purchase_history": orders}

    return await dpage_with_action(
        f"https://www.amazon.com/your-orders/orders?timeFilter=year-{target_year}",
        action=get_order_details_action,
    )


@amazon_mcp.tool
async def get_purchase_history(
    year: str | int | None = None, start_index: int = 0
) -> dict[str, Any]:
    """Get purchase/order history of a amazon with dpage."""

    if year is None:
        target_year = datetime.now().year
    elif isinstance(year, str):
        try:
            target_year = int(year)
        except ValueError:
            target_year = datetime.now().year
    else:
        target_year = int(year)

    current_year = datetime.now().year
    if not (1900 <= target_year <= current_year + 1):
        raise ValueError(f"Year {target_year} is out of valid range (1900-{current_year + 1})")

    return await dpage_mcp_tool(
        f"https://www.amazon.com/your-orders/orders?timeFilter=year-{target_year}&startIndex={start_index}",
        "amazon_purchase_history",
    )


# Track if timing log file has been setup
_timing_log_setup = False


def setup_timing_log_file(log_filename: str = "amazon_patchright_timing.log"):
    """Setup a file handler specifically for timing logs."""
    global _timing_log_setup

    if _timing_log_setup:
        return

    from pathlib import Path

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / log_filename

    # Add a file sink for timing logs only
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
        filter=lambda record: "TIMING" in record["message"],
        rotation="10 MB",
        retention="7 days",
        enqueue=True,
    )
    _timing_log_setup = True
    logger.info(f"[PATCHRIGHT_TIMING] Timing logs will be saved to: {log_path.absolute()}")
    return log_path


@amazon_mcp.tool
async def get_purchase_history_with_details(
    year: str | int | None = None, start_index: int = 0, timeFilter: str | None = None
) -> dict[str, Any]:
    """Get purchase/order history of a amazon with dpage."""

    # Setup timing log file on first call
    setup_timing_log_file()

    if year is None:
        target_year = datetime.now().year
    elif isinstance(year, str):
        try:
            target_year = int(year)
        except ValueError:
            target_year = datetime.now().year
    else:
        target_year = int(year)

    if timeFilter is None:
        timeFilter = f"year-{target_year}"

    current_year = datetime.now().year
    if not (1900 <= target_year <= current_year + 1):
        raise ValueError(f"Year {target_year} is out of valid range (1900-{current_year + 1})")

    async def get_order_details_action(
        page: Page, browser_profile: BrowserProfile
    ) -> dict[str, Any]:
        action_start_time = time.time()
        logger.info(
            f"[PATCHRIGHT_TIMING] ===== Starting get_purchase_history_with_details (timeFilter={timeFilter}, startIndex={start_index}) ====="
        )

        current_url = page.url
        if "signin" in current_url:
            raise Exception("User is not signed in")

        path = os.path.join(os.path.dirname(__file__), "patterns", "**/amazon-*.html")

        patterns_start = time.time()
        logger.info(f"[PATCHRIGHT_TIMING] Loading patterns from {path}")
        patterns = load_distillation_patterns(path)
        patterns_time = time.time() - patterns_start
        logger.info(f"[PATCHRIGHT_TIMING] Loaded {len(patterns)} patterns in {patterns_time:.3f}s")

        distillation_start = time.time()
        logger.info(f"[PATCHRIGHT_TIMING] Starting distillation loop")
        _, _, orders = await run_distillation_loop(
            f"https://www.amazon.com/your-orders/orders?timeFilter={timeFilter}&startIndex={start_index}",
            patterns,
            browser_profile=browser_profile,
            interactive=False,
            timeout=2,
            page=page,
        )
        distillation_time = time.time() - distillation_start
        logger.info(f"[PATCHRIGHT_TIMING] Distillation loop completed in {distillation_time:.3f}s")

        if orders is None:
            total_time = time.time() - action_start_time
            logger.info(f"[PATCHRIGHT_TIMING] No orders found, total time: {total_time:.3f}s")
            return {"amazon_purchase_history": []}

        normalize_start = time.time()
        logger.info(f"[PATCHRIGHT_TIMING] Normalizing {len(orders)} order IDs")
        for order in orders:
            order["order_id"] = normalize_order_id(order.get("order_id")) or ""
        normalize_time = time.time() - normalize_start
        logger.info(
            f"[PATCHRIGHT_TIMING] Order ID normalization completed in {normalize_time:.3f}s"
        )

        # Initialize timing variables in case of exceptions
        gather_time = 0.0
        processing_time = 0.0

        async def get_order_details(order: dict[str, Any]):
            order_start = time.time()
            order_id = order["order_id"]
            store_logo = order.get("store_logo")
            logger.info(f"[PATCHRIGHT_TIMING] Fetching details for order: {order_id}")

            # If we already have product prices, return early
            product_prices = order.get("product_prices")
            if isinstance(product_prices, list):
                elapsed = time.time() - order_start
                logger.info(
                    f"[PATCHRIGHT_TIMING] Order {order_id} already has prices, skipped in {elapsed:.3f}s"
                )
                return {"order_id": order_id}

            # Determine order type based on brand logo alt text
            order_type = "regular"
            if store_logo:
                store_logo_text = str(store_logo).lower()
                if "whole foods" in store_logo_text:
                    order_type = "wholefoods"
                elif "fresh" in store_logo_text:
                    order_type = "fresh"

            match order_type:
                case "wholefoods":
                    # Use Whole Foods URL format
                    url = f"https://www.amazon.com/fopo/order-details?orderID={order_id}&ref=ppx_yo2ov_dt_b_fed_wwgs_wfm_ATVPDKIKX0DER&page=itemmod"
                    result = await page.evaluate(f"""
                        async () => {{
                            const res = await fetch('{url}', {{
                                method: 'GET',
                                credentials: 'include',
                            }});
                            const text = await res.text();
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(text, 'text/html');
                            doc.querySelectorAll('script').forEach(s => s.remove());

                            const itemRows = doc.querySelectorAll('div.a-row.a-spacing-base');
                            const prices = [];
                            const productNames = [];
                            const productUrls = [];
                            const imageUrls = [];

                            itemRows.forEach(row => {{
                                const productLink = row.querySelector('div.a-column.a-span10 > a.a-size-small.a-link-normal');
                                if (productLink) {{
                                    const name = productLink.textContent?.trim();
                                    if (name) {{
                                        productNames.push(name);
                                    }}
                                    const href = productLink.getAttribute('href');
                                    if (href) {{
                                        productUrls.push(href);
                                    }}
                                }}

                                const priceSpan = row.querySelector('div.a-column.a-span2.a-span-last div.a-text-right span.a-size-small');
                                if (priceSpan) {{
                                    prices.push(priceSpan.textContent?.trim() || '');
                                }}

                                const img = row.querySelector('img.ufpo-itemListWidget-image');
                                if (img) {{
                                    const src = img.getAttribute('src') || img.getAttribute('data-a-hires');
                                    if (src) {{
                                        imageUrls.push(src);
                                    }}
                                }}
                            }});
                            let paymentInfo = "";
                            if (doc.querySelector("span#wfm-0-card-brand")){{
                                paymentInfo = doc.querySelector("span#wfm-0-card-brand")?.textContent?.trim() + " " + doc.querySelector("span#wfm-0-card-tail")?.textContent?.trim();
                            }}
                            return {{
                                prices,
                                productNames,
                                productUrls,
                                imageUrls,
                                paymentInfo
                            }};
                        }}
                    """)
                    elapsed = time.time() - order_start
                    logger.info(
                        f"[PATCHRIGHT_TIMING] Order {order_id} (wholefoods) details fetched in {elapsed:.3f}s"
                    )
                    return {"order_id": order_id, **result}

                case "fresh":
                    # Use Fresh URL format
                    url = f"https://www.amazon.com/uff/your-account/order-details?orderID={order_id}&ref=ppx_yo2ov_dt_b_fed_wwgs_yo_odp_A1VC38T7YXB528&page=itemmod"
                    result = await page.evaluate(f"""
                        async () => {{
                            const res = await fetch('{url}', {{
                                method: 'GET',
                                credentials: 'include',
                            }});
                            const text = await res.text();
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(text, 'text/html');
                            doc.querySelectorAll('script').forEach(s => s.remove());

                            const itemRows = doc.querySelectorAll('div[id$="-item-grid-row"]');
                            const prices = [];
                            const productNames = [];
                            const productUrls = [];
                            const imageUrls = [];

                            itemRows.forEach(row => {{
                                const priceSpan = row.querySelector('span[id$="-item-total-price"]');
                                if (priceSpan) {{
                                    prices.push(priceSpan.textContent?.trim() || '');
                                }}

                                const productLink = row.querySelector('a.a-link-normal.a-text-normal');
                                if (productLink) {{
                                    const nameSpan = productLink.querySelector('span');
                                    if (nameSpan) {{
                                        const name = nameSpan.textContent?.trim();
                                        if (name) {{
                                            productNames.push(name);
                                        }}
                                    }}
                                    const href = productLink.getAttribute('href');
                                    if (href) {{
                                        productUrls.push(href);
                                    }}
                                }}

                                const img = row.querySelector('div.ufpo-item-image-column img');
                                if (img) {{
                                    const src = img.getAttribute('src') || img.getAttribute('data-a-hires');
                                    if (src) {{
                                        imageUrls.push(src);
                                    }}
                                }}
                            }});

                            const paymentInfo = doc.querySelector("li.pmts-payments-instrument-detail-box-paystationpaymentmethod")?.textContent?.trim();
                            const paymentInfoDetail = doc.querySelector("li.pmts-payments-instrument-detail-box-paystationpaymentmethod:nth-of-type(2)")?.textContent?.trim();
                            let paymentMethod = "";
                            let paymentGiftCardAmount = "";
                            if (paymentInfoDetail?.includes("gift card")){{
                                paymentMethod = "GIFT_CARD";
                                paymentGiftCardAmount = doc.querySelector("span#ufpo-giftCardAmount-amount")?.textContent?.trim();
                            }}
                            
                            return {{
                                prices,
                                productNames,
                                productUrls,
                                imageUrls,
                                paymentInfo,
                                paymentInfoDetail
                            }};
                        }}
                    """)
                    elapsed = time.time() - order_start
                    logger.info(
                        f"[PATCHRIGHT_TIMING] Order {order_id} (fresh) details fetched in {elapsed:.3f}s"
                    )
                    return {"order_id": order_id, **result}

                case _:
                    # Use regular order URL format
                    url = f"https://www.amazon.com/gp/css/summary/print.html?orderID={order_id}&ref=ppx_yo2ov_dt_b_fed_invoice_pos"
                    result = await page.evaluate(f"""
                        async () => {{
                            const res = await fetch('{url}', {{
                                method: 'GET',
                                credentials: 'include',
                            }});
                            const text = await res.text();
                            const parser = new DOMParser();
                            const doc = parser.parseFromString(text, 'text/html');
                            doc.querySelectorAll('script').forEach(s => s.remove());

                            const rows = doc.querySelectorAll("div.a-fixed-left-grid");
                            const prices = Array.from(rows)
                                .map(row => row.querySelector("span.a-price span.a-offscreen")?.textContent?.trim())
                                .filter(Boolean);
                                
                            const paymentElement = doc.querySelector("div.pmts-payment-instrument-billing-address");
                            const paymentInfoElements = Array.from(doc.querySelectorAll("span.pmts-payments-instrument-detail-box-paystationpaymentmethod"));
                            
                            const isGiftCard = !!paymentInfoElements?.find(el => el.textContent?.toLowerCase().includes("gift card"));
                            
                            // This element only exists for BNPL orders
                            const bnplElement = paymentElement?.querySelector("span.pmts-payments-instrument-supplemental-box-paystationpaymentmethod");
                            
                            let paymentInfo = paymentInfoElements[0]?.textContent?.trim();
                            let paymentInfoDetail = "";
                            let paymentGiftCardAmount = "";
                            let paymentMethod = "";
                            
                            
                            if (bnplElement) {{
                                paymentInfoDetail = bnplElement?.textContent?.trim();
                                paymentMethod = "BNPL";
                            }} else if (isGiftCard) {{
                                paymentInfoDetail = paymentInfoElements[0]?.textContent?.trim();
                                paymentInfo = paymentInfoElements[1]?.textContent?.trim();
                                if (paymentInfo?.includes("gift card")){{
                                    paymentInfoDetail = paymentInfoElements[1]?.textContent?.trim();
                                    paymentInfo = paymentInfoElements[0]?.textContent?.trim();
                                }}
                                paymentGiftCardAmount = Array.from(doc.querySelectorAll("div#od-subtotals span.a-list-item"))
                                                            .find(el => el.textContent?.includes("Gift Card"))
                                                            ?.querySelector("div.a-span-last")
                                                            ?.textContent
                                                            ?.trim();
                                paymentMethod = "GIFT_CARD";
                            }}
                            
                            return {{
                                prices,
                                paymentInfo,
                                paymentInfoDetail,
                                paymentGiftCardAmount,
                                paymentMethod,
                            }};
                        }}
                    """)
                    elapsed = time.time() - order_start
                    logger.info(
                        f"[PATCHRIGHT_TIMING] Order {order_id} (regular) details fetched in {elapsed:.3f}s"
                    )
                    return {"order_id": order_id, **result}

        try:
            gather_start = time.time()
            logger.info(
                f"[PATCHRIGHT_TIMING] Starting parallel fetch of {len(orders)} order details"
            )
            order_details_list = await asyncio.gather(
                *[get_order_details(order) for order in orders], return_exceptions=True
            )
            gather_time = time.time() - gather_start
            logger.info(
                f"[PATCHRIGHT_TIMING] All order details fetched in {gather_time:.3f}s (parallel)"
            )

            error_count = 0
            for i, item in enumerate(order_details_list):
                if isinstance(item, BaseException):
                    error_count += 1
                    order_id = orders[i]["order_id"]
                    logger.warning(
                        f"[PATCHRIGHT_TIMING] Error getting order details for order: {order_id}: {item}"
                    )

            if error_count > 0:
                logger.warning(
                    f"[PATCHRIGHT_TIMING] {error_count}/{len(orders)} orders failed to fetch details"
                )

            processing_start = time.time()
            logger.info(f"[PATCHRIGHT_TIMING] Processing and merging order details")
            order_details = {
                item["order_id"]: item
                for item in order_details_list
                if not isinstance(item, BaseException)
            }
            for order in orders:
                details = order_details.get(order["order_id"])
                if details is None:
                    continue
                if details.get("prices") is not None:
                    order["product_prices"] = details["prices"]
                # For Fresh/Whole Foods orders, replace product information with the complete details
                if order.get("store_logo") and details.get("productNames"):
                    order["product_names"] = details["productNames"]
                    order["product_urls"] = details["productUrls"]
                    order["image_urls"] = details["imageUrls"]
                order["payment_info"] = details.get("paymentInfo") or ""
                order["payment_info_detail"] = details.get("paymentInfoDetail") or ""
                order["payment_method"] = details.get("paymentMethod") or ""
                order["payment_gift_card_amount"] = details.get("paymentGiftCardAmount") or ""
            processing_time = time.time() - processing_start
            logger.info(
                f"[PATCHRIGHT_TIMING] Order details processing completed in {processing_time:.3f}s"
            )
        except Exception as e:
            logger.error(f"Error getting order details for order: {e}")
            pass

        total_time = time.time() - action_start_time
        logger.info(f"[PATCHRIGHT_TIMING] ===== TOTAL TIME: {total_time:.3f}s =====")
        logger.info(
            f"[PATCHRIGHT_TIMING] BREAKDOWN: patterns={patterns_time:.3f}s | distillation={distillation_time:.3f}s | normalize={normalize_time:.3f}s | fetch={gather_time:.3f}s | processing={processing_time:.3f}s"
        )
        return {"amazon_purchase_history": orders}

    return await dpage_with_action(
        f"https://www.amazon.com/your-orders/orders?timeFilter={timeFilter}&startIndex={start_index}",
        action=get_order_details_action,
    )
