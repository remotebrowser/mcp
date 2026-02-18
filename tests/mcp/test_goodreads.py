"""Tests for Goodreads Tools: login, get_book_list."""

import json
import os
from typing import Any

import pytest
import zendriver as zd
from fastmcp import Client
from mcp.types import TextContent


@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.xfail(reason="flaky")
async def test_goodreads_login_and_get_book_list(mcp_config: dict[str, Any]):
    """Test login to goodreads."""
    client = Client(mcp_config, timeout=120)
    async with client:
        mcp_call_tool = await client.call_tool("goodreads_get_book_list")
        assert isinstance(mcp_call_tool.content[0], TextContent), (
            f"Expected TextContent, got {type(mcp_call_tool.content[0])}"
        )
        mcp_call_signin_result = json.loads(mcp_call_tool.content[0].text)
        assert mcp_call_signin_result.get("url")
        assert mcp_call_signin_result.get("signin_id")
        print(mcp_call_signin_result.get("url"))

        browser = await zd.start(no_sandbox=True, headless=True)
        try:
            page = await browser.get(mcp_call_signin_result.get("url"))

            email_input = await page.wait_for("input[type=email]")
            await email_input.send_keys(os.environ.get("GOODREADS_EMAIL", ""))
            password_input = await page.wait_for("input[type=password]")
            await password_input.send_keys(os.environ.get("GOODREADS_PASSWORD", ""))
            submit_btn = await page.select("button[type='submit']")
            await submit_btn.click()

            await page.wait_for(text="Finished!", timeout=30)

            mcp_call_check_signin = await client.call_tool(
                "check_signin", {"signin_id": mcp_call_signin_result.get("signin_id")}
            )
            assert isinstance(mcp_call_check_signin.content[0], TextContent), (
                f"Expected TextContent, got {type(mcp_call_check_signin.content[0])}"
            )
            mcp_call_check_signin_result = json.loads(mcp_call_check_signin.content[0].text)
            assert mcp_call_check_signin_result.get("status") == "SUCCESS"

            mcp_call_get_results = await client.call_tool("goodreads_get_book_list")
            assert isinstance(mcp_call_get_results.content[0], TextContent), (
                f"Expected TextContent, got {type(mcp_call_get_results.content[0])}"
            )
            parsed_mcp_call_result = json.loads(mcp_call_get_results.content[0].text)
            book_list = parsed_mcp_call_result.get("goodreads_book_list")
            print(book_list)
            assert book_list, "Expected 'book_list' to be non-empty"
            assert isinstance(book_list, list), f"Expected list, got {type(book_list)}"
        finally:
            await browser.stop()
