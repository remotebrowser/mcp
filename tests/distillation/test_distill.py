import os
import urllib.parse
from pathlib import Path
from typing import Any, cast

import pytest
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from pytest import MonkeyPatch

from getgather.config import settings
from getgather.distill import load_distillation_patterns
from getgather.zen_distill import (
    distill,
    get_new_page,
    init_zendriver_browser,
    run_distillation_loop,
    terminate_zendriver_browser,
)

DISTILL_PATTERN_LOCATIONS = {
    "http://localhost:5001": "acme_home_page.html",
    "http://localhost:5001/auth/email-and-password": "acme_email_and_password.html",
    "http://localhost:5001/auth/email-then-password": "acme_email_only.html",
    "http://localhost:5001/auth/email-and-password-checkbox": "acme_email_and_password_checkbox.html",
    "http://localhost:5001/universal-error-test": "acme_universal_error_test.html",
}

SIGN_IN_PATTERN_ENDPOINTS = [
    "http://localhost:5001/auth/email-and-password",
    "http://localhost:5001/auth/email-and-password-checkbox",
    "http://localhost:5001/auth/email-then-password",
    "http://localhost:5001/auth/email-then-otp",
    "http://localhost:5001/auth/email-and-password-then-mfa",
]


@pytest.mark.asyncio
@pytest.mark.distill
@pytest.mark.parametrize(
    "location",
    list(DISTILL_PATTERN_LOCATIONS.keys()),
)
async def test_distill_form_fields(location: str):
    """Tests the distill function's most basic ability to match a simple pattern."""
    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)
    assert patterns, "No patterns found to begin matching."

    browser = await init_zendriver_browser()
    try:
        page = await get_new_page(browser)
        hostname = urllib.parse.urlparse(location).hostname
        await page.get(location)
        await page.wait(3)

        match = await distill(hostname, page, patterns)
        assert match, "No match found when one was expected."
        assert match.name.endswith(DISTILL_PATTERN_LOCATIONS[location]), (
            "Incorrect match name found."
        )
    finally:
        await terminate_zendriver_browser(browser)


@pytest.mark.asyncio
@pytest.mark.distill
@pytest.mark.parametrize("location", SIGN_IN_PATTERN_ENDPOINTS)
async def test_distillation_loop(location: str):
    """Tests distillation loop with email and password autofill."""
    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)
    assert patterns, "No patterns found to begin matching."

    browser = await init_zendriver_browser()
    try:
        _terminated, distilled, converted = await run_distillation_loop(
            location=location,
            patterns=patterns,
            browser=browser,
            timeout=30,
            interactive=True,
        )
        result = converted if converted else distilled
        assert result, "No result found when one was expected."
    finally:
        await terminate_zendriver_browser(browser)


# Map error endpoints to expected pattern names (production patterns)
BROWSER_ERROR_ENDPOINTS = {
    "http://localhost:5001/error/timed-out": "err-timed-out.html",
    "http://localhost:5001/error/ssl-protocol-error": "err-ssl-protocol-error.html",
    "http://localhost:5001/error/tunnel-connection-failed": "err-tunnel-connection-failed.html",
    "http://localhost:5001/error/proxy-connection-failed": "err-proxy-connection-failed.html",
}


@pytest.mark.asyncio
@pytest.mark.distill
async def test_distillation_captures_screenshot_without_pattern(
    tmp_path: Path, monkeypatch: MonkeyPatch
):
    """Navigates to a page without patterns and verifies a screenshot is saved."""

    monkeypatch.setattr(cast(Any, settings), "DATA_DIR", str(tmp_path), raising=False)

    screenshot_dir: Path = settings.screenshots_dir
    before = set(screenshot_dir.glob("*.png"))

    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)
    assert patterns, "No patterns found to begin matching."

    browser = await init_zendriver_browser()
    try:
        terminated, _distilled, _converted = await run_distillation_loop(
            location="http://localhost:5001/random-info-page",
            patterns=patterns,
            browser=browser,
            timeout=2,
            interactive=False,
        )

        assert not terminated, "Expected not to terminate when no pattern matches."

        after = set(screenshot_dir.glob("*.png"))
        new_files = [item for item in after if item not in before]
        assert new_files, "Expected a distillation screenshot to be captured."
        assert all(file.stat().st_size > 0 for file in new_files)
    finally:
        await terminate_zendriver_browser(browser)


@pytest.mark.asyncio
@pytest.mark.distill
@pytest.mark.parametrize("location", list(BROWSER_ERROR_ENDPOINTS.keys()))
async def test_browser_error_patterns(location: str):
    """
    Tests for browser error page pattern matching.

    Tests that error patterns (ERR_TIMED_OUT, ERR_SSL_PROTOCOL_ERROR, etc.)
    are correctly matched.

    These tests use the production patterns from getgather/mcp/patterns/err-*.html
    to ensure the actual patterns work correctly.
    """
    path = str(PROJECT_ROOT / "getgather" / "mcp" / "patterns" / "err-*.html")
    patterns = load_distillation_patterns(path)
    assert patterns, "No patterns found"

    browser = await init_zendriver_browser()
    try:
        page = await get_new_page(browser)
        hostname = urllib.parse.urlparse(location).hostname

        await page.get(location)
        await page.wait(1)

        match = await distill(hostname, page, patterns, reload_on_error=False)
        assert match, f"No match found for {location}"
        assert match.name.endswith(BROWSER_ERROR_ENDPOINTS[location]), (
            f"Expected pattern {BROWSER_ERROR_ENDPOINTS[location]}, got {match.name}"
        )
    finally:
        await terminate_zendriver_browser(browser)
