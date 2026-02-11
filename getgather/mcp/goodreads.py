from typing import Any

import zendriver as zd
from loguru import logger

from getgather.mcp.dpage import (
    remote_zen_dpage_mcp_tool,
    remote_zen_dpage_with_action,
    zen_dpage_with_action,
)
from getgather.mcp.registry import GatherMCP
from getgather.zen_distill import page_query_selector
from getgather.mcp.ui import UI_MIME_TYPE, ToolUI
from mcp_ui_server import create_ui_resource, UIResource

GOODREADS_SIGNIN_UI_URI = "ui://goodreads/signin"
GOODREADS_TEST_UI_URI = "ui://goodreads/test"
GOODREADS_TEST_APP_URI = "ui://goodreads/test-app"

goodreads_app_ui = ToolUI(resource_uri=GOODREADS_TEST_APP_URI)  # pyright: ignore[reportCallIssue]
goodreads_mcp = GatherMCP(
    brand_id="goodreads",
    name="Goodreads MCP",
    app_ui=goodreads_app_ui,
)

_signin_url: str | None = None


@goodreads_mcp.resource(uri=GOODREADS_SIGNIN_UI_URI)
async def _goodreads_signin_ui_resource() -> str:  # pyright: ignore[reportUnusedFunction]
    """Serve minimal HTML that redirects to the Goodreads sign-in URL."""
    signin_url = "https://example.com"
    return (
        "<!DOCTYPE html>"
        "<html>"
        "<head>"
        f'<meta http-equiv="refresh" content="0;url={signin_url}">'
        "</head>"
        "<body>"
        f'<p><a href="{signin_url}">Click here to sign in</a></p>'
        "</body>"
        "</html>"
    )


@goodreads_mcp.tool(meta=goodreads_mcp.app_ui_tool_meta())
async def show_signin_ui(signin_id: str) -> list[UIResource]:
    """Open the Goodreads sign-in UI so the user can enter credentials. Call this with the signin_id returned by get_book_list when sign-in is required. The UI will receive this signin_id and use it when calling submit_dpage_signin."""
    ui_resource = create_ui_resource({
        "uri": GOODREADS_SIGNIN_UI_URI,
        "content": {
            "type": "externalUrl",
            "iframeUrl": "https://example.com"
        },
        "encoding": "text"
    })
    return [ui_resource]


# For testing mcp ui mechanism
@goodreads_mcp.tool
async def show_test_ui() -> list[UIResource]:
    """Open a test UI resource that renders http://example.com. This is for testing purposes only."""
    ui_resource = create_ui_resource({
        "uri": GOODREADS_TEST_UI_URI,
        "content": {
            "type": "externalUrl",
            "iframeUrl": "http://example.com"
        },
        "encoding": "text"
    })
    return [ui_resource]


@goodreads_mcp.resource(uri=GOODREADS_TEST_APP_URI, mime_type=UI_MIME_TYPE)
async def _goodreads_test_app_resource() -> str:  # pyright: ignore[reportUnusedFunction]
    """Serve HTML resource that returns http://example.com for testing purposes."""
    return "<html><meta http-equiv='refresh' content='0;url=http://example.com'></meta><body></body></html>"


# For testing mcp apps mechanism
@goodreads_mcp.tool(meta=goodreads_mcp.app_ui_tool_meta())
async def show_test_app() -> dict[str, str]:
    """Show the test app."""
    return {
        "message": "Howdy!",
    }


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

# For testing combined mcp apps and ui mechanism
@goodreads_mcp.tool(meta=goodreads_mcp.app_ui_tool_meta())
async def show_test_app_and_ui() -> list[UIResource]:
    """Show the test app and ui."""
    ui_resource = create_ui_resource({
        "uri": GOODREADS_TEST_APP_URI,
        "content": {
            "type": "externalUrl",
            "iframeUrl": "http://example.com"
        },
        "encoding": "text"
    })
    return [ui_resource]


@goodreads_mcp.tool
async def get_book_list() -> dict[str, Any]:
    """Get the book list from a user's Goodreads account."""
    global _signin_url

    result = await remote_zen_dpage_mcp_tool(
        "https://www.goodreads.com/review/list?ref=nav_mybooks&view=table", "goodreads_book_list"
    )
    signin_id_val = result.get("signin_id")
    if signin_id_val:
        _signin_url = result.get("url") or None
        result["ui_resource_uri"] = GOODREADS_SIGNIN_UI_URI
        result["system_message"] = (
            "Sign-in is required. Call show_signin_ui with the signin_id from this response so the user can sign in. "
            "After the user submits the form, you can call check_signin(signin_id) to get the result, or the result may be returned directly from submit_dpage_signin."
        )
    return result


@goodreads_mcp.tool
async def remote_get_book_list() -> dict[str, Any]:
    """Get the book list from a user's Goodreads account."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.goodreads.com/review/list?ref=nav_mybooks&view=table", "goodreads_book_list"
    )


@goodreads_mcp.tool
async def get_book_details(book_url: str) -> dict[str, Any]:
    """Get details (title, author, rating, description) of a book on Goodreads.

    Args:
        book_url: Full Goodreads book URL, e.g. https://www.goodreads.com/book/show/12345
    """
    return await zen_dpage_with_action(
        initial_url=book_url,
        action=_goodreads_book_details_action,
    )


@goodreads_mcp.tool
async def remote_get_book_details(book_url: str) -> dict[str, Any]:
    """Get details (title, author, rating, description) of a book on Goodreads.

    Args:
        book_url: Full Goodreads book URL, e.g. https://www.goodreads.com/book/show/12345
    """
    return await remote_zen_dpage_with_action(
        initial_url=book_url,
        action=_goodreads_book_details_action,
    )
