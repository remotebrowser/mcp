from typing import Any

from getgather.mcp.dpage import zen_dpage_mcp_tool
from getgather.mcp.registry import AppUIConfig, GatherMCP

GOODREADS_SIGNIN_UI_URI = "ui://goodreads/signin"

goodreads_app_ui = AppUIConfig(
    resource_uri=GOODREADS_SIGNIN_UI_URI,
)
goodreads_mcp = GatherMCP(
    brand_id="goodreads",
    name="Goodreads MCP",
    app_ui=goodreads_app_ui,
)

_signin_url: str | None = None


@goodreads_mcp.resource(uri=GOODREADS_SIGNIN_UI_URI)
async def _goodreads_signin_ui_resource() -> str:  # pyright: ignore[reportUnusedFunction]
    """Serve minimal HTML that redirects to the Goodreads sign-in URL."""
    if not _signin_url:
        return "<!DOCTYPE html><html><body><p>No sign-in URL available. Please try again.</p></body></html>"
    return f'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url={_signin_url}"></head><body><p><a href="{_signin_url}">Click here to sign in</a></p></body></html>'


@goodreads_mcp.tool(meta=goodreads_app_ui.tool_meta())
async def show_signin_ui(signin_id: str) -> dict[str, Any]:
    """Open the Goodreads sign-in UI so the user can enter credentials. Call this with the signin_id returned by get_book_list when sign-in is required. The UI will receive this signin_id and use it when calling submit_dpage_signin."""
    return {
        "signin_id": signin_id,
        "ui_resource_uri": GOODREADS_SIGNIN_UI_URI,
        "message": "Enter your Goodreads credentials in the sign-in form.",
    }


@goodreads_mcp.tool
async def get_book_list() -> dict[str, Any]:
    """Get the book list from a user's Goodreads account."""
    global _signin_url

    result = await zen_dpage_mcp_tool(
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
