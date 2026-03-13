"""Tests for ESPN Tools: get_schedule."""

import json
from typing import Any

import pytest
from fastmcp import Client
from mcp.types import TextContent


@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.xfail(reason="flaky")
async def test_espn_get_schedule(mcp_config: dict[str, Any]):
    """Test get schedule from ESPN."""
    client = Client(mcp_config, timeout=120)
    async with client:
        mcp_call_result = await client.call_tool("espn_get_schedule")
        assert isinstance(mcp_call_result.content[0], TextContent), (
            f"Expected TextContent, got {type(mcp_call_result.content[0])}"
        )
        parsed_mcp_call_result = json.loads(mcp_call_result.content[0].text)
        schedule = parsed_mcp_call_result.get("college_football_schedule")
        assert schedule, "Expected 'college_football_schedule' to be non-empty"
        assert isinstance(schedule, list), f"Expected list, got {type(schedule)}"
