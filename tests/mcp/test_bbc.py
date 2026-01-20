"""Tests for BBC Tools: login, get_bookmarks."""

import json
import os

import pytest
import zendriver as zd
from fastmcp import Client
from mcp.types import TextContent

config = {
    "mcpServers": {"getgather": {"url": f"{os.environ.get('HOST', 'http://localhost:23456')}/mcp"}}
}


@pytest.mark.mcp
@pytest.mark.asyncio
async def test_bbc_login_and_get_bookmarks():
    """Test login to bbc."""
    client = Client(config)
    async with client:
        mcp_call_tool = await client.call_tool("bbc_get_saved_articles")
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
            await email_input.send_keys(os.environ.get("BBC_EMAIL", ""))
            submit_btn = await page.select("button[type='submit']")
            await submit_btn.click()

            password_input = await page.wait_for("input[type=password]")
            await password_input.send_keys(os.environ.get("BBC_PASSWORD", ""))
            submit_btn = await page.select("button[type='submit']")
            await submit_btn.click()

            await page.wait_for("text=Finished! You can close this window now.")

            mcp_call_check_signin = await client.call_tool(
                "check_signin", {"signin_id": mcp_call_signin_result.get("signin_id")}
            )
            assert isinstance(mcp_call_check_signin.content[0], TextContent), (
                f"Expected TextContent, got {type(mcp_call_check_signin.content[0])}"
            )
            mcp_call_check_signin_result = json.loads(mcp_call_check_signin.content[0].text)
            assert mcp_call_check_signin_result.get("status") == "SUCCESS"

            mcp_call_get_results = await client.call_tool("bbc_get_saved_articles")
            assert isinstance(mcp_call_get_results.content[0], TextContent), (
                f"Expected TextContent, got {type(mcp_call_get_results.content[0])}"
            )
            parsed_mcp_call_result = json.loads(mcp_call_get_results.content[0].text)
            saved_articles = parsed_mcp_call_result.get("saved_articles")
            print(saved_articles)
            assert saved_articles, "Expected 'saved_articles' to be non-empty"
            assert isinstance(saved_articles, list), f"Expected list, got {type(saved_articles)}"
        finally:
            await browser.stop()
