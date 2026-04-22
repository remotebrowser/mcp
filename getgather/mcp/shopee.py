from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import MCPTool

SHOPEE_TIMEOUT_SECONDS = 15

shopee_mcp = MCPTool(brand_id="shopee", name="Shopee MCP")


@shopee_mcp.tool
async def get_purchase_history() -> dict[str, Any]:
    """Get purchase history of a shopee."""
    return await remote_zen_dpage_mcp_tool(
        "https://shopee.co.id/user/purchase",
        "shopee_purchase_history",
        timeout=SHOPEE_TIMEOUT_SECONDS,
    )


@shopee_mcp.tool
async def search_product(keyword: str, page_number: int = 1) -> dict[str, Any]:
    """Search product on shopee."""
    url = f"https://shopee.co.id/search?keyword={keyword}"
    return await remote_zen_dpage_mcp_tool(
        url,
        "shopee_search_product",
        timeout=SHOPEE_TIMEOUT_SECONDS,
    )
