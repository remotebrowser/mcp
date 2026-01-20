"""
Tests for browser error page pattern matching.

Tests that error patterns (ERR_TIMED_OUT, ERR_SSL_PROTOCOL_ERROR, etc.)
are correctly matched using XPath selectors that work with both
Playwright and zendriver.

These tests use the production patterns from getgather/mcp/patterns/err-*.html
to ensure the actual patterns work correctly.
"""

import os
import urllib.parse

import pytest
from dotenv import load_dotenv

load_dotenv()

from getgather.browser.profile import BrowserProfile
from getgather.browser.session import browser_session
from getgather.distill import distill as playwright_distill, load_distillation_patterns

# Map error endpoints to expected pattern names (production patterns)
BROWSER_ERROR_ENDPOINTS = {
    "http://localhost:5001/error/timed-out": "err-timed-out.html",
    "http://localhost:5001/error/ssl-protocol-error": "err-ssl-protocol-error.html",
    "http://localhost:5001/error/tunnel-connection-failed": "err-tunnel-connection-failed.html",
    "http://localhost:5001/error/proxy-connection-failed": "err-proxy-connection-failed.html",
}


def get_patterns():
    """Load production error patterns from getgather/mcp/patterns/."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "getgather", "mcp", "patterns", "err-*.html"
    )
    return load_distillation_patterns(path)


@pytest.mark.asyncio
@pytest.mark.distill
@pytest.mark.parametrize("location", list(BROWSER_ERROR_ENDPOINTS.keys()))
async def test_browser_error_patterns_playwright(location: str):
    """Test browser error patterns with Playwright."""
    profile = BrowserProfile()
    patterns = get_patterns()
    assert patterns, "No patterns found"

    async with browser_session(profile) as session:
        page = await session.page()
        hostname = urllib.parse.urlparse(location).hostname
        await page.goto(location)

        match = await playwright_distill(hostname, page, patterns)
        assert match, f"No match found for {location}"
        assert match.name.endswith(BROWSER_ERROR_ENDPOINTS[location]), (
            f"Expected pattern {BROWSER_ERROR_ENDPOINTS[location]}, got {match.name}"
        )
