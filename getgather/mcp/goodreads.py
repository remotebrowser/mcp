from typing import Any

import zendriver as zd
from loguru import logger

from getgather.browser import page_query_selector
from getgather.mcp.app_ui_html_renderer import book_list_content_template, render_app_ui_html
from getgather.mcp.dpage import (
    get_base_url,
    remote_zen_dpage_mcp_tool,
    remote_zen_dpage_with_action,
)
from getgather.mcp.registry import MCPTool
from getgather.mcp.ui import UI_MIME_TYPE, ResourceCSP, ToolUI

GOODREADS_UI_URI = "ui://list/data?brand=goodreads"

goodreads_app_ui = ToolUI(
    resourceUri=GOODREADS_UI_URI,
    csp=ResourceCSP(
        resourceDomains=["https://i.gr-assets.com"],
        frameDomains=["self", get_base_url()],
    ),
)

goodreads_mcp = MCPTool(
    brand_id="goodreads",
    name="Goodreads MCP",
    app_ui=goodreads_app_ui,
)


async def _goodreads_book_details_action(tab: zd.Tab, _browser: zd.Browser) -> dict[str, Any]:
    title_el = await page_query_selector(tab, "h1.Text__title1", timeout=10)
    title = await title_el.inner_text() if title_el else None

    author_el = await page_query_selector(tab, "span.ContributorLink__name", timeout=5)
    author = await author_el.inner_text() if author_el else None

    rating_el = await page_query_selector(tab, "div.RatingStatistics__rating", timeout=5)
    rating = await rating_el.inner_text() if rating_el else None

    desc_el = await page_query_selector(
        tab, "div.DetailsLayoutRightParagraph span.Formatted", timeout=5
    )
    description = await desc_el.inner_text() if desc_el else None

    details: dict[str, Any] = {}
    if title:
        details["title"] = title
    if author:
        details["author"] = author
    if rating:
        details["rating"] = rating
    if description:
        details["description"] = description

    if not details:
        logger.warning("Could not extract any book details from the page")

    return {"goodreads_book_details": details}


@goodreads_mcp.resource(uri=GOODREADS_UI_URI, mime_type=UI_MIME_TYPE)
async def goodreads_ui_resource() -> str:
    """Serve the book list app. Host pushes get_book_list result via ontoolresult"""
    return render_app_ui_html(content=book_list_content_template(), title="Goodreads MCP App")


@goodreads_mcp.tool(meta=goodreads_mcp.app_ui_tool_meta())
async def get_book_list() -> dict[str, Any]:
    """Get the book list from a user's Goodreads account."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.goodreads.com/review/list?ref=nav_mybooks&view=table",
        "goodreads_book_list",
    )


@goodreads_mcp.tool
async def get_book_details(book_url: str) -> dict[str, Any]:
    """Get details (title, author, rating, description) of a book on Goodreads.

    Args:
        book_url: Full Goodreads book URL, e.g. https://www.goodreads.com/book/show/12345
    """
    return await remote_zen_dpage_with_action(
        initial_url=book_url,
        action=_goodreads_book_details_action,
    )
