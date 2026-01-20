"""Tests for BBC Tools: login, get_bookmarks."""

import json
import os

import pytest
from fastmcp import Client
from mcp.types import TextContent
from patchright.async_api import async_playwright

config = {
    "mcpServers": {"getgather": {"url": f"{os.environ.get('HOST', 'http://localhost:23456')}/mcp"}}
}


@pytest.mark.mcp
@pytest.mark.asyncio
async def test_bbc_login_and_get_bookmarks():
    """Test login to bbc."""
    async with async_playwright() as p:
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

            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            await page.goto(url=mcp_call_signin_result.get("url"), wait_until="domcontentloaded")

            await page.wait_for_selector("input[type=email]")
            await page.type("input[type=email]", os.environ.get("BBC_EMAIL", ""))
            await page.click("button[type='submit']")

            await page.wait_for_selector("input[type=password]")
            await page.type("input[type=password]", os.environ.get("BBC_PASSWORD", ""))
            await page.click("button[type='submit']")

            await page.wait_for_selector(":has-text('Finished! You can close this window now.')")

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
