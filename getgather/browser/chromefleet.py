from typing import Literal, cast
from urllib.parse import urlparse

import asyncio_atexit
import httpx
import zendriver as zd
from fastmcp.server.dependencies import get_http_headers
from httpx_retries import Retry, RetryTransport
from loguru import logger
from zendriver.core import util
from zendriver.core._contradict import ContraDict
from zendriver.core.config import Config
from zendriver.core.connection import Connection

from getgather.config import settings

HTTP_METHOD = Literal["GET", "POST", "DELETE"]


async def _create_browser_from_cdp_websocket(
    websocket_url: str, config: Config | None = None
) -> zd.Browser:
    parsed = urlparse(websocket_url)
    host = parsed.hostname or "127.0.0.1"
    host = f"[{host.strip('[]')}]" if ":" in host else host  # handle ipv6 addresses
    port = parsed.port or (443 if parsed.scheme in ("wss", "https") else 80)

    if not config:
        config = Config(host=host, port=port)

    config.host = host
    config.port = port

    instance = zd.Browser(config)
    instance.info = ContraDict({"webSocketDebuggerUrl": websocket_url}, silent=True)
    instance.connection = Connection(websocket_url, _owner=instance)

    if instance.config.autodiscover_targets:
        instance.connection.handlers[zd.cdp.target.TargetInfoChanged] = [  # type: ignore[reportUnknownMemberType]
            instance._handle_target_update  # type: ignore[reportPrivateUsage]
        ]
        instance.connection.handlers[zd.cdp.target.TargetCreated] = [instance._handle_target_update]  # type: ignore[reportUnknownMemberType,reportPrivateUsage]
        instance.connection.handlers[zd.cdp.target.TargetDestroyed] = [  # type: ignore[reportUnknownMemberType]
            instance._handle_target_update  # type: ignore[reportPrivateUsage]
        ]
        instance.connection.handlers[zd.cdp.target.TargetCrashed] = [instance._handle_target_update]  # type: ignore[reportUnknownMemberType,reportPrivateUsage]
        await instance.connection.send(zd.cdp.target.set_discover_targets(discover=True))

    await instance.update_targets()
    util.get_registered_instances().add(instance)

    async def browser_atexit() -> None:
        if not instance.stopped:
            await instance.stop()
        await instance._cleanup_temporary_profile()  # type: ignore[reportPrivateUsage]

    asyncio_atexit.register(browser_atexit)  # type: ignore[reportUnknownMemberType]

    return instance


async def _call_chromefleet_api(
    method: HTTP_METHOD,
    browser_id: str,
    *,
    timeout: float = 120.0,
    retries: int = 3,
    raise_for_status: bool = True,
) -> httpx.Response:
    base_url = settings.CHROMEFLEET_URL.rstrip("/")
    if not base_url:
        raise ValueError("CHROMEFLEET_URL is not configured")

    url = f"{base_url}/api/v1/browsers/{browser_id}"

    mcp_headers = get_http_headers(include_all=True)
    headers = {
        "x-forwarded-for": mcp_headers.get("x-forwarded-for", None),
        "user-agent": mcp_headers.get("user-agent", None),
        "sec-ch-ua": mcp_headers.get("sec-ch-ua", None),
        "sec-ch-ua-mobile": mcp_headers.get("sec-ch-ua-mobile", None),
        "sec-ch-ua-platform": mcp_headers.get("sec-ch-ua-platform", None),
        "x-location": mcp_headers.get("x-location", None),
        "x-proxy-type": mcp_headers.get("x-proxy-type", None),
    }
    headers = {k: v for k, v in headers.items() if v is not None}

    async with httpx.AsyncClient(
        transport=RetryTransport(
            retry=Retry(
                total=retries,
                backoff_factor=1.0,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=[method],
            )
        ),
    ) as client:
        response = await client.request(
            method,
            url,
            headers=headers,
            timeout=httpx.Timeout(connect=2.0, pool=None, read=timeout, write=timeout),
        )
        if raise_for_status:
            response.raise_for_status()
        return response


async def get_remote_browser(browser_id: str) -> zd.Browser | None:
    logger.info(f"Finding the ChromeFleet browser: {browser_id}")
    try:
        response = await _call_chromefleet_api("GET", browser_id)
        if response.status_code != 200:
            return None
    except Exception:
        return None

    cdp_base = settings.CHROMEFLEET_URL.replace("https://", "wss://").replace("http://", "ws://")
    cdp_websocket_url = f"{cdp_base}/cdp/{browser_id}"
    logger.debug(f"Connecting to ChromeFleet CDP at {cdp_websocket_url}")
    browser = await _create_browser_from_cdp_websocket(cdp_websocket_url)
    browser.id = browser_id  # type: ignore[attr-defined]
    return browser


async def create_remote_browser(browser_id: str) -> zd.Browser:
    """
    Start a remote Chrome via ChromeFleet and connect via CDP.
    The browser_id must not already be in use.
    """
    logger.info(f"Starting new ChromeFleet browser: {browser_id}")
    await _call_chromefleet_api("POST", browser_id)
    cdp_base = settings.CHROMEFLEET_URL.replace("https://", "wss://").replace("http://", "ws://")
    cdp_websocket_url = f"{cdp_base}/cdp/{browser_id}"
    logger.debug(f"Connecting to ChromeFleet CDP at {cdp_websocket_url}")
    browser = await _create_browser_from_cdp_websocket(cdp_websocket_url)
    browser.id = browser_id  # type: ignore[attr-defined]
    return browser


async def terminate_remote_browser(browser: zd.Browser) -> None:
    """Terminate an existing remote Chrome via ChromeFleet."""
    browser_id = cast(str, browser.id)  # type: ignore[attr-defined]
    logger.info(f"Terminating ChromeFleet browser: {browser_id}")
    # no need to raise for error (which would fail the whole process)
    await _call_chromefleet_api(
        "DELETE", browser_id, timeout=5.0, retries=0, raise_for_status=False
    )
