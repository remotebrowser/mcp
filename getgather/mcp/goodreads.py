from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent
from mcp_ui_server import UIResource, create_ui_resource

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP
from getgather.mcp.ui import UI_MIME_TYPE, ToolUI

GOODREADS_SIGNIN_UI_URI = "ui://goodreads/signin"
GOODREADS_TEST_UI_URI = "ui://goodreads/test"
GOODREADS_TEST_APP_URI = "ui://goodreads/test-app"

# goodreads_app_ui = ToolUI(resource_uri=GOODREADS_TEST_APP_URI)  # pyright: ignore[reportCallIssue]
goodreads_app_ui = ToolUI(resource_uri=GOODREADS_SIGNIN_UI_URI)  # pyright: ignore[reportCallIssue]
goodreads_mcp = GatherMCP(
    brand_id="goodreads",
    name="Goodreads MCP",
    # This is used only for mcp apps
    # app_ui=goodreads_app_ui,
    # app_ui=goodreads_app_ui,
)

_signin_url: str | None = None


@goodreads_mcp.resource(uri=GOODREADS_SIGNIN_UI_URI)
async def _goodreads_signin_ui_resource() -> str:  # pyright: ignore[reportUnusedFunction]
    """Serve minimal HTML that redirects to the Goodreads sign-in URL."""
    # signin_url = "https://example.com"
    signin_url = _signin_url
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


# @goodreads_mcp.tool(meta=goodreads_mcp.app_ui_tool_meta())
# async def show_signin_ui(signin_id: str) -> list[UIResource]:
#     """Open the Goodreads sign-in UI so the user can enter credentials. Call this with the signin_id returned by get_book_list when sign-in is required. The UI will receive this signin_id and use it when calling submit_dpage_signin."""
#     ui_resource = create_ui_resource({
#         "uri": GOODREADS_SIGNIN_UI_URI,
#         "content": {
#             "type": "externalUrl",
#             "iframeUrl": "https://example.com"
#         },
#         "encoding": "text"
#     })
#     return [ui_resource]


# For testing mcp ui mechanism
@goodreads_mcp.tool
async def show_test_ui() -> list[UIResource]:
    """Open a test UI resource that renders http://example.com. This is for testing purposes only."""
    ui_resource = create_ui_resource({
        "uri": GOODREADS_TEST_UI_URI,
        "content": {"type": "externalUrl", "iframeUrl": "http://example.com"},
        "encoding": "text",
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


# For testing combined mcp apps and ui mechanism
@goodreads_mcp.tool(meta=goodreads_mcp.app_ui_tool_meta())
async def show_test_app_and_ui() -> list[UIResource]:
    """Show the test app and ui."""
    ui_resource = create_ui_resource({
        "uri": GOODREADS_TEST_APP_URI,
        "content": {"type": "externalUrl", "iframeUrl": "http://example.com"},
        "encoding": "text",
    })
    return [ui_resource]


@goodreads_mcp.tool
async def get_book_list() -> ToolResult:
    """Get the book list from a user's Goodreads account."""
    result = await zen_dpage_mcp_tool(
        "https://www.goodreads.com/review/list?ref=nav_mybooks&view=table", "goodreads_book_list"
    )
    signin_id = result.get("signin_id")
    signin_url = result.get("url") or None
    if signin_id and signin_url:
        ui_resource = create_ui_resource({
            "uri": f"ui://dpage/{signin_id}",
            "content": {
                "type": "externalUrl",
                "iframeUrl": signin_url,
            },
            "uiMetadata": {"preferred-frame-size": ["100%", "500px"]},
            "encoding": "text",
            "metadata": result,
        })
        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=str(result),
                ),
                ui_resource,
            ],
            structured_content=result,
        )

    return ToolResult(
        content=result,
        structured_content=result,
    )
