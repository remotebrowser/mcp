"""Tests for NPR Tools: get_headlines."""

import json
from typing import Any

import pytest
from fastmcp import Client
from mcp.types import TextContent


@pytest.mark.mcp
@pytest.mark.asyncio
async def test_npr_get_headlines(mcp_config: dict[str, Any]):
    """Test get headlines from NPR."""
    client = Client(mcp_config)
    async with client:
        mcp_call_result = await client.call_tool("npr_get_headlines")
        assert isinstance(mcp_call_result.content[0], TextContent), (
            f"Expected TextContent, got {type(mcp_call_result.content[0])}"
        )
        parsed_mcp_call_result = json.loads(mcp_call_result.content[0].text)
        headlines = parsed_mcp_call_result.get("headlines")
        assert headlines, "Expected 'headlines' to be non-empty"
        assert isinstance(headlines, list), f"Expected list, got {type(headlines)}"
