"""Tests for remote sign-in polling in dpage_check."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest import MonkeyPatch

from getgather.mcp import dpage as dpage_module
from getgather.mcp.dpage import completed_signins, dpage_check


@pytest.fixture(autouse=True)
def clear_completed_signins():
    completed_signins.clear()
    yield
    completed_signins.clear()


async def _instant_sleep(_delay: float = 0) -> None:
    return None


@pytest.mark.asyncio
async def test_dpage_check_remote_aborted_when_tab_gone_without_completed_signin(
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr("getgather.mcp.dpage.asyncio.sleep", _instant_sleep)

    async def fake_get_remote_browser(_browser_id: str):
        browser = MagicMock()
        browser.tabs = []
        return browser

    monkeypatch.setattr(dpage_module, "get_remote_browser", fake_get_remote_browser)

    result = await dpage_check("remoteBrowser--pageTarget123")
    assert result is False


@pytest.mark.asyncio
async def test_dpage_check_remote_success_from_completed_signins_before_poll(
    monkeypatch: MonkeyPatch,
):
    monkeypatch.setattr("getgather.mcp.dpage.asyncio.sleep", _instant_sleep)

    sid = "remoteBrowser--pageTarget123"
    completed_signins.add(sid)

    async def should_not_run() -> None:
        raise AssertionError("get_remote_browser should not run when completed_signins is set")

    monkeypatch.setattr(dpage_module, "get_remote_browser", should_not_run)

    result = await dpage_check(sid)
    assert result is True
    assert sid not in completed_signins


@pytest.mark.asyncio
async def test_dpage_check_remote_survives_distill_exception(monkeypatch: MonkeyPatch):
    monkeypatch.setattr("getgather.mcp.dpage.asyncio.sleep", _instant_sleep)

    page = MagicMock()
    page.target_id = "pageTarget123"
    page.url = "https://example.com/"
    page.evaluate = AsyncMock(return_value="https://example.com/")

    browser = MagicMock()
    browser.tabs = [page]

    async def fake_get_remote_browser(_browser_id: str):
        return browser

    calls = {"n": 0}

    async def fake_distill(*_args: object, **_kwargs: object) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated tab detach during distill")
        return None

    monkeypatch.setattr(dpage_module, "get_remote_browser", fake_get_remote_browser)
    monkeypatch.setattr(dpage_module, "zen_distill", fake_distill)

    result = await dpage_check("remoteBrowser--pageTarget123")
    assert result is None
    assert calls["n"] >= 2
