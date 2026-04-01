import os
import urllib.parse
from pathlib import Path
from typing import Any, cast

import pytest
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from nanoid import generate
from pytest import MonkeyPatch

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ACME_HOSTNAME = "https://acme.fly.dev"

from getgather.browser.chromefleet import create_remote_browser, terminate_remote_browser
from getgather.config import FRIENDLY_CHARS, settings
from getgather.zen_distill import (
    Pattern,
    batch_check_visibility,
    batch_extract_distill_targets,
    collect_distill_targets,
    distill,
    get_new_page,
    load_distillation_patterns,
    run_distillation_loop,
)

DISTILL_PATTERN_LOCATIONS = {
    "/": "acme_home_page.html",
    "/auth/email-and-password": "acme_email_and_password.html",
    "/auth/email-then-password": "acme_email_only.html",
    "/auth/email-and-password-checkbox": "acme_email_and_password_checkbox.html",
    "/universal-error-test": "acme_universal_error_test.html",
}

SIGN_IN_PATTERN_ENDPOINTS = [
    "/auth/email-and-password",
    "/auth/email-and-password-checkbox",
    "/auth/email-then-password",
    "/auth/email-then-otp",
    "/auth/email-and-password-then-mfa",
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

    url = f"{ACME_HOSTNAME}{location}"
    browser = await create_remote_browser(browser_id=generate(FRIENDLY_CHARS, 6))
    try:
        page = await get_new_page(browser)
        hostname = urllib.parse.urlparse(url).hostname
        await page.get(url)
        await page.wait(3)

        match = await distill(hostname, page, patterns)
        assert match, "No match found when one was expected."
        assert match.name.endswith(DISTILL_PATTERN_LOCATIONS[location]), (
            "Incorrect match name found."
        )
    finally:
        await terminate_remote_browser(browser)


@pytest.mark.asyncio
@pytest.mark.distill
@pytest.mark.parametrize("location", SIGN_IN_PATTERN_ENDPOINTS)
async def test_distillation_loop(location: str):
    """Tests distillation loop with email and password autofill."""
    path = os.path.join(os.path.dirname(__file__), "patterns", "**/*.html")
    patterns = load_distillation_patterns(path)
    assert patterns, "No patterns found to begin matching."

    browser = await create_remote_browser(browser_id=generate(FRIENDLY_CHARS, 6))
    try:
        _terminated, distilled, converted = await run_distillation_loop(
            location=f"{ACME_HOSTNAME}{location}",
            patterns=patterns,
            browser=browser,
            timeout=30,
            interactive=True,
        )
        result = converted if converted else distilled
        assert result, "No result found when one was expected."
    finally:
        await terminate_remote_browser(browser)


# Map error endpoints to expected pattern names (production patterns)
BROWSER_ERROR_ENDPOINTS = {
    "/error/timed-out": "err-timed-out.html",
    "/error/ssl-protocol-error": "err-ssl-protocol-error.html",
    "/error/tunnel-connection-failed": "err-tunnel-connection-failed.html",
    "/error/proxy-connection-failed": "err-proxy-connection-failed.html",
}


class StubPage:
    def __init__(self, result: object):
        self.result = result
        self.calls: list[str] = []

    async def evaluate(self, js_code: str):
        self.calls.append(js_code)
        return self.result


@pytest.mark.asyncio
async def test_batch_check_visibility_returns_boolean_results():
    page = StubPage([True, None, False, 1, 0])

    result = await batch_check_visibility(
        cast(Any, page),
        [
            {"selector": "h1", "is_xpath": False},
            {"selector": "p", "is_xpath": False},
            {"selector": "//div", "is_xpath": True},
            {"selector": "input", "is_xpath": False},
            {"selector": "", "is_xpath": False},
        ],
    )

    assert result == [True, False, False, True, False]
    assert len(page.calls) == 1


@pytest.mark.asyncio
async def test_batch_check_visibility_falls_back_to_all_false_on_invalid_result():
    page = StubPage(None)

    result = await batch_check_visibility(
        cast(Any, page),
        [
            {"selector": "h1", "is_xpath": False},
            {"selector": "//div", "is_xpath": True},
        ],
    )

    assert result == [False, False]
    assert len(page.calls) == 1


@pytest.mark.asyncio
async def test_batch_extract_distill_targets_returns_css_and_xpath_payloads():
    page = StubPage(
        [
            {
                "found": True,
                "visible": True,
                "tag": "h1",
                "text": "Welcome",
                "html": "<span>Welcome</span>",
                "value": "",
            },
            {
                "found": True,
                "visible": True,
                "tag": "section",
                "text": "Account",
                "html": "<p>Account</p>",
                "value": "",
            },
        ]
    )

    result = await batch_extract_distill_targets(
        cast(Any, page),
        [
            {"selector": "h1", "is_xpath": False},
            {"selector": "//section[@data-role='account']", "is_xpath": True},
        ],
    )

    assert result == [
        {
            "found": True,
            "visible": True,
            "tag": "h1",
            "text": "Welcome",
            "html": "<span>Welcome</span>",
            "value": "",
        },
        {
            "found": True,
            "visible": True,
            "tag": "section",
            "text": "Account",
            "html": "<p>Account</p>",
            "value": "",
        },
    ]
    assert len(page.calls) == 1


@pytest.mark.asyncio
async def test_batch_extract_distill_targets_preserves_missing_and_hidden_payloads():
    page = StubPage(
        [
            {
                "found": False,
                "visible": False,
                "tag": "",
                "text": "",
                "html": "",
                "value": "",
            },
            {
                "found": True,
                "visible": False,
                "tag": "div",
                "text": "Hidden",
                "html": "<span>Hidden</span>",
                "value": "",
            },
        ]
    )

    result = await batch_extract_distill_targets(
        cast(Any, page),
        [
            {"selector": ".missing", "is_xpath": False},
            {"selector": ".hidden", "is_xpath": False},
        ],
    )

    assert result == [
        {
            "found": False,
            "visible": False,
            "tag": "",
            "text": "",
            "html": "",
            "value": "",
        },
        {
            "found": True,
            "visible": False,
            "tag": "div",
            "text": "Hidden",
            "html": "<span>Hidden</span>",
            "value": "",
        },
    ]
    assert len(page.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("tag_name", ["input", "select", "textarea"])
async def test_batch_extract_distill_targets_preserves_form_values(tag_name: str):
    page = StubPage(
        [
            {
                "found": True,
                "visible": True,
                "tag": tag_name,
                "text": "",
                "html": "",
                "value": "prefilled",
            }
        ]
    )

    result = await batch_extract_distill_targets(
        cast(Any, page),
        [{"selector": tag_name, "is_xpath": False}],
    )

    assert result == [
        {
            "found": True,
            "visible": True,
            "tag": tag_name,
            "text": "",
            "html": "",
            "value": "prefilled",
        }
    ]
    assert len(page.calls) == 1


@pytest.mark.asyncio
async def test_batch_extract_distill_targets_falls_back_on_invalid_result():
    page = StubPage({"found": True})

    result = await batch_extract_distill_targets(
        cast(Any, page),
        [
            {"selector": "h1", "is_xpath": False},
            {"selector": "//div", "is_xpath": True},
        ],
    )

    assert result == [
        {
            "found": False,
            "visible": False,
            "tag": "",
            "text": "",
            "html": "",
            "value": "",
        },
        {
            "found": False,
            "visible": False,
            "tag": "",
            "text": "",
            "html": "",
            "value": "",
        },
    ]
    assert len(page.calls) == 1


def test_collect_distill_targets_extracts_selector_metadata():
    pattern = BeautifulSoup(
        """
        <html gg-priority="1">
            <button gg-match="button.login"></button>
            <input gg-match="iframe.auth input[type='email']" gg-optional />
            <div gg-match-html="//section[@data-role='content']"></div>
            <span></span>
        </html>
        """,
        "html.parser",
    )

    targets = collect_distill_targets(pattern)

    assert len(targets) == 3

    assert targets[0].selector == "button.login"
    assert targets[0].iframe_selector is None
    assert targets[0].is_html is False
    assert targets[0].optional is False

    assert targets[1].selector == "input[type='email']"
    assert targets[1].iframe_selector == "iframe.auth"
    assert targets[1].is_html is False
    assert targets[1].optional is True

    assert targets[2].selector == "//section[@data-role='content']"
    assert targets[2].iframe_selector is None
    assert targets[2].is_html is True
    assert targets[2].optional is False


@pytest.mark.asyncio
async def test_distill_preserves_iframe_selector_lookup(monkeypatch: MonkeyPatch):
    class StubElement:
        tag = "div"
        element = {}

        async def inner_text(self) -> str:
            return "Sign in"

    async def stub_batch_check_visibility(
        page: Any, selectors: list[dict[str, str | bool]]
    ) -> list[bool]:
        return [False] * len(selectors)

    async def stub_page_query_selector(
        page: Any,
        selector: str,
        timeout: float = 0,
        iframe_selector: str | None = None,
        skip_visibility_check: bool = False,
        config: Any = None,
    ) -> StubElement | None:
        if selector == "button.login" and iframe_selector == "iframe.auth":
            return StubElement()
        return None

    monkeypatch.setattr("getgather.zen_distill.batch_check_visibility", stub_batch_check_visibility)
    monkeypatch.setattr("getgather.zen_distill.page_query_selector", stub_page_query_selector)

    pattern = Pattern(
        name="iframe-login.html",
        pattern=BeautifulSoup(
            '<html gg-priority="1"><button gg-match="iframe.auth button.login"></button></html>',
            "html.parser",
        ),
    )

    match = await distill("example.com", cast(Any, object()), [pattern], reload_on_error=False)

    assert match is not None
    assert match.name == "iframe-login.html"
    assert "Sign in" in match.distilled


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

    browser = await create_remote_browser(browser_id=generate(FRIENDLY_CHARS, 6))
    try:
        terminated, _distilled, _converted = await run_distillation_loop(
            location=f"{ACME_HOSTNAME}/random-info-page",
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
        await terminate_remote_browser(browser)


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

    url = f"{ACME_HOSTNAME}{location}"
    browser = await create_remote_browser(browser_id=generate(FRIENDLY_CHARS, 6))
    try:
        page = await get_new_page(browser)
        hostname = urllib.parse.urlparse(url).hostname

        await page.get(url)
        await page.wait(1)

        match = await distill(hostname, page, patterns, reload_on_error=False)
        assert match, f"No match found for {url}"
        assert match.name.endswith(BROWSER_ERROR_ENDPOINTS[location]), (
            f"Expected pattern {BROWSER_ERROR_ENDPOINTS[location]}, got {match.name}"
        )
    finally:
        await terminate_remote_browser(browser)
