from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool, zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

wayfair_mcp = GatherMCP(brand_id="wayfair", name="Wayfair MCP")


@wayfair_mcp.tool
async def get_order_history(page_number: int = 1) -> dict[str, Any]:
    """Get order history of wayfair."""
    return await zen_dpage_mcp_tool(
        f"https://www.wayfair.com/session/secure/account/order_search.php?page={page_number}",
        "wayfair_order_history",
    )


@wayfair_mcp.tool
async def remote_get_order_history(page_number: int = 1) -> dict[str, Any]:
    """Get order history of wayfair."""
    return await remote_zen_dpage_mcp_tool(
        f"https://www.wayfair.com/session/secure/account/order_search.php?page={page_number}",
        "wayfair_order_history",
    )


@wayfair_mcp.tool
async def get_order_history_details(order_id: str) -> dict[str, Any]:
    """Get order history details of wayfair."""
    return await zen_dpage_mcp_tool(
        f"https://www.wayfair.com/v/account/order/details?order_id={order_id}",
        "wayfair_order_history_details",
        timeout=30,
    )


@wayfair_mcp.tool
async def remote_get_order_history_details(order_id: str) -> dict[str, Any]:
    """Get order history details of wayfair."""
    return await remote_zen_dpage_mcp_tool(
        f"https://www.wayfair.com/v/account/order/details?order_id={order_id}",
        "wayfair_order_history_details",
        timeout=30,
    )


@wayfair_mcp.tool
async def get_cart() -> dict[str, Any]:
    """Get order history details of wayfair."""
    return await zen_dpage_mcp_tool(
        "https://www.wayfair.com/v/checkout/basket/show", "wayfair_cart", timeout=30
    )


@wayfair_mcp.tool
async def remote_get_cart() -> dict[str, Any]:
    """Get order history details of wayfair."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.wayfair.com/v/checkout/basket/show", "wayfair_cart", timeout=30
    )


@wayfair_mcp.tool
async def get_wishlists() -> dict[str, Any]:
    """Get wishlists of wayfair."""
    return await zen_dpage_mcp_tool(
        "https://www.wayfair.com/lists", "wayfair_wishlists", timeout=30
    )


@wayfair_mcp.tool
async def remote_get_wishlists() -> dict[str, Any]:
    """Get wishlists of wayfair."""
    return await remote_zen_dpage_mcp_tool(
        "https://www.wayfair.com/lists", "wayfair_wishlists", timeout=30
    )


@wayfair_mcp.tool
async def get_wishlist_details(url: str) -> dict[str, Any]:
    """Get wishlist details of wayfair."""
    return await zen_dpage_mcp_tool(
        f"https://www.wayfair.com{url}", "wayfair_wishlist_details", timeout=30
    )


@wayfair_mcp.tool
async def remote_get_wishlist_details(url: str) -> dict[str, Any]:
    """Get wishlist details of wayfair."""
    return await remote_zen_dpage_mcp_tool(
        f"https://www.wayfair.com{url}", "wayfair_wishlist_details", timeout=30
    )
