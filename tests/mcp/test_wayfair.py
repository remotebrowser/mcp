"""Tests for Wayfair Tools: login, get_order_history"""

import json
import os
from typing import Any

import pytest
import zendriver as zd
from dotenv import load_dotenv
from fastmcp import Client
from mcp.types import TextContent

load_dotenv()


@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.xfail(reason="flaky")
async def test_wayfair_login_and_get_order_history(mcp_config: dict[str, Any]):
    """Test login to wayfair and get order history."""
    client = Client(mcp_config, timeout=120)
    async with client:
        mcp_call_tool = await client.call_tool("wayfair_get_order_history")
        assert isinstance(mcp_call_tool.content[0], TextContent), (
            f"Expected TextContent, got {type(mcp_call_tool.content[0])}"
        )
        mcp_call_signin_result = json.loads(mcp_call_tool.content[0].text)
        assert mcp_call_signin_result.get("url")
        assert mcp_call_signin_result.get("signin_id")
        print(mcp_call_signin_result.get("url"))

        browser = await zd.start(headless=False)
        try:
            page = await browser.get(mcp_call_signin_result.get("url"))

            email_input = await page.wait_for("input[type=email]")
            await email_input.send_keys(os.environ.get("WAYFAIR_EMAIL", ""))
            submit_btn = await page.select("button[type='submit']")
            await submit_btn.click()

            # Wait for password option and click it
            password_option = await page.wait_for("text=Sign In With Your Password")
            await password_option.click()

            password_input = await page.wait_for("input[type=password]")
            await password_input.send_keys(os.environ.get("WAYFAIR_PASSWORD", ""))
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
            assert mcp_call_check_signin_result.get("completed") is True
            assert "result" not in mcp_call_check_signin_result

            mcp_call_get_order_history = await client.call_tool("wayfair_get_order_history")
            assert isinstance(mcp_call_get_order_history.content[0], TextContent), (
                f"Expected TextContent, got {type(mcp_call_get_order_history.content[0])}"
            )
            parsed_mcp_call_result = json.loads(mcp_call_get_order_history.content[0].text)
            order_history = parsed_mcp_call_result.get("wayfair_order_history")
            print(order_history)
            assert order_history, "Expected 'order_history' to be non-empty"
            assert isinstance(order_history, list), f"Expected list, got {type(order_history)}"
        finally:
            await browser.stop()


@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.xfail(reason="flaky")
async def test_wayfair_get_cart(mcp_config: dict[str, Any]):
    """Test get cart from wayfair."""
    client = Client(mcp_config, timeout=120)
    async with client:
        mcp_call_get_cart = await client.call_tool("wayfair_get_cart")
        assert isinstance(mcp_call_get_cart.content[0], TextContent), (
            f"Expected TextContent, got {type(mcp_call_get_cart.content[0])}"
        )
        parsed_mcp_call_result = json.loads(mcp_call_get_cart.content[0].text)
        cart = parsed_mcp_call_result.get("wayfair_cart")
        print(cart)
        assert cart, "Expected 'cart' to be non-empty"
        assert isinstance(cart, list), f"Expected list, got {type(cart)}"


@pytest.mark.mcp
@pytest.mark.asyncio
@pytest.mark.xfail(reason="flaky")
async def test_wayfair_get_wishlists(mcp_config: dict[str, Any]):
    """Test get wishlists from wayfair."""
    client = Client(mcp_config, timeout=120)
    async with client:
        mcp_call_get_wishlists = await client.call_tool("wayfair_get_wishlists")
        assert isinstance(mcp_call_get_wishlists.content[0], TextContent), (
            f"Expected TextContent, got {type(mcp_call_get_wishlists.content[0])}"
        )
        parsed_mcp_call_result = json.loads(mcp_call_get_wishlists.content[0].text)
        wishlists = parsed_mcp_call_result.get("wayfair_wishlists")
        print(wishlists)
        assert wishlists, "Expected 'wishlists' to be non-empty"
        assert isinstance(wishlists, list), f"Expected list, got {type(wishlists)}"
