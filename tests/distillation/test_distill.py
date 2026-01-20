import os
import urllib.parse
from pathlib import Path
from typing import Any, cast

import pytest
from dotenv import load_dotenv
from pytest import MonkeyPatch

# Load environment variables from .env file
load_dotenv()

from getgather.config import settings
from getgather.distill import load_distillation_patterns
from getgather.zen_distill import (
    distill,
    get_new_page,
    init_zendriver_browser,
    run_distillation_loop,
    zen_navigate_with_retry,
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
async def test_distill(location: str):
    """Tests the distill function's most basic ability to match a simple pattern."""
    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)
    assert patterns, "No patterns found to begin matching."

    browser = await init_zendriver_browser(headless=True)
    try:
        page = await get_new_page(browser)
        hostname = urllib.parse.urlparse(location).hostname

        await zen_navigate_with_retry(page, location)

        match = await distill(hostname, page, patterns)
        assert match, "No match found when one was expected."
        assert match.name.endswith(DISTILL_PATTERN_LOCATIONS[location]), (
            "Incorrect match name found."
        )
    finally:
        await browser.stop()


@pytest.mark.asyncio
@pytest.mark.distill
@pytest.mark.parametrize(
    "location",
    SIGN_IN_PATTERN_ENDPOINTS,
)
async def test_distillation_loop(location: str):
    """Tests the distillation loop with email and password autofill."""
    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)
    assert patterns, "No patterns found to begin matching."

    browser = await init_zendriver_browser(headless=True)
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
        await browser.stop()


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

    browser = await init_zendriver_browser(headless=True)
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
        await browser.stop()
