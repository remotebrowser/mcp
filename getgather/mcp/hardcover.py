from typing import Any

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

hardcover_mcp = GatherMCP(brand_id="hardcover", name="Hardcover MCP")


@hardcover_mcp.tool
async def get_book_list() -> dict[str, Any]:
    """Get book list from Hardcover.app."""
    return await remote_zen_dpage_mcp_tool("https://hardcover.app", "hardcover_book_list")
