import types

import pytest

from getgather.browser import chromefleet


@pytest.mark.asyncio
async def test_wait_for_cdp_formats_ipv6(monkeypatch):
    requested_url: dict[str, str] = {}

    class DummyResponse:
        status_code = 200

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, timeout):
            requested_url["url"] = str(url)
            return DummyResponse()

    monkeypatch.setattr(chromefleet.httpx, "AsyncClient", lambda *args, **kwargs: DummyClient())

    await chromefleet._wait_for_cdp("fdaa:40:8b11:0:1::4", 9222, timeout_s=0.1)

    assert (
        requested_url["url"] == "http://[fdaa:40:8b11:0:1::4]:9222/json/list"
    ), "IPv6 hosts should be wrapped in brackets for CDP polling"


@pytest.mark.asyncio
async def test_connect_over_cdp_brackets_ipv6(monkeypatch):
    calls: dict[str, str | int] = {}

    async def fake_wait_for_cdp(host: str, port: int, timeout_s: float = 30.0) -> None:
        calls["wait_host"] = host
        calls["wait_port"] = port

    async def fake_create(*args, **kwargs):
        calls["create_host"] = kwargs.get("host")
        calls["create_port"] = kwargs.get("port")
        return types.SimpleNamespace()

    monkeypatch.setattr(chromefleet, "_wait_for_cdp", fake_wait_for_cdp)
    monkeypatch.setattr(chromefleet.zd.Browser, "create", fake_create)

    browser = await chromefleet._connect_over_cdp(
        "browser-123", "http://[fdaa:40:8b11:0:1::4]:9222"
    )

    assert calls["wait_host"] == "[fdaa:40:8b11:0:1::4]"
    assert calls["create_host"] == "[fdaa:40:8b11:0:1::4]"
    assert browser.id == "browser-123"


def test_parse_cdp_endpoint_with_unbracketed_ipv6():
    host, port = chromefleet._parse_cdp_endpoint("http://fdaa:40:8b11:0:1::7:9222")
    assert host == "[fdaa:40:8b11:0:1::7]"
    assert port == 9222


def test_parse_cdp_endpoint_with_bracketed_ipv6():
    host, port = chromefleet._parse_cdp_endpoint("http://[fdaa:40:8b11:0:1::7]:9222")
    assert host == "[fdaa:40:8b11:0:1::7]"
    assert port == 9222


def test_parse_cdp_endpoint_with_ipv4():
    host, port = chromefleet._parse_cdp_endpoint("http://10.0.0.5:9333")
    assert host == "10.0.0.5"
    assert port == 9333


def test_parse_cdp_endpoint_invalid_url():
    with pytest.raises(ValueError):
        chromefleet._parse_cdp_endpoint("http:///json/list")


def test_parse_cdp_endpoint_missing_host():
    with pytest.raises(ValueError):
        chromefleet._parse_cdp_endpoint("http://:9222")


def test_parse_cdp_endpoint_empty_brackets():
    with pytest.raises(ValueError):
        chromefleet._parse_cdp_endpoint("http://[]:9222")


@pytest.mark.asyncio
async def test_validated_cdp_url_retries(monkeypatch):
    calls: list[str] = []

    class DummyResponse:
        def __init__(self, url: str):
            self._url = url

        def json(self):
            return {"cdp_url": self._url}

    async def fake_call(endpoint: str, browser_id: str):
        calls.append(endpoint)
        if len(calls) == 1:
            return DummyResponse("http://:9222")
        return DummyResponse("http://127.0.0.1:9333")

    sleep_calls: list[float] = []

    async def fake_sleep(delay: float):
        sleep_calls.append(delay)

    monkeypatch.setattr(chromefleet, "_call_chromefleet_api", fake_call)
    monkeypatch.setattr(chromefleet.asyncio, "sleep", fake_sleep)

    cdp_url, host, port = await chromefleet._validated_cdp_url("abc123", endpoint="start", attempts=2)

    assert cdp_url == "http://127.0.0.1:9333"
    assert host == "127.0.0.1"
    assert port == 9333
    assert calls == ["start", "query"]
    assert sleep_calls, "Expected a retry delay when the first URL is invalid"
