from typing import Any

from fastmcp import Context

from getgather.mcp.dpage import remote_zen_dpage_mcp_tool
from getgather.mcp.registry import GatherMCP

bbc_mcp = GatherMCP(brand_id="bbc", name="BBC MCP")


@bbc_mcp.tool
async def get_saved_articles(ctx: Context) -> dict[str, Any]:
    """Get the list of saved articles from BBC news site"""

    return await remote_zen_dpage_mcp_tool("https://www.bbc.com/saved", "saved_articles")
