"""Tests for Calendar Tools: create_calendar_event."""

import json
from typing import Any

import pytest
from fastmcp import Client
from mcp.types import TextContent


@pytest.mark.mcp
@pytest.mark.asyncio
async def test_calendar_create_calendar_event(mcp_config: dict[str, Any]):
    """Test creating a calendar event returns valid ICS content."""
    client = Client(mcp_config, timeout=120)
    async with client:
        mcp_call_result = await client.call_tool(
            "calendar_create_calendar_event",
            {"title": "Test Event", "event_date": "2026-06-01"},
        )
        assert isinstance(mcp_call_result.content[0], TextContent), (
            f"Expected TextContent, got {type(mcp_call_result.content[0])}"
        )
        parsed = json.loads(mcp_call_result.content[0].text)
        assert "ics_content" in parsed, "Expected 'ics_content' in result"
        assert "BEGIN:VCALENDAR" in parsed["ics_content"]
        assert "Test Event" in parsed["ics_content"]
        event_details = parsed.get("event_details")
        assert event_details, "Expected 'event_details' in result"
        assert event_details["title"] == "Test Event"
