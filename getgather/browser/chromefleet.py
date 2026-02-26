import asyncio
from typing import Literal, cast
from urllib.parse import urlparse

import httpx
import websockets
import zendriver as zd
from loguru import logger
from zendriver.core import util
from zendriver.core._contradict import ContraDict
from zendriver.core.browser import HTTPApi
from zendriver.core.config import Config
from zendriver.core.connection import Connection

from getgather.config import settings

HTTP_METHOD = Literal["GET", "POST", "DELETE"]


def _build_cdp_websocket_url(browser_id: str) -> str:
    """Construct the CDP WebSocket URL via ChromeFleet's /cdp/{browser_id} proxy."""
    base = settings.CHROMEFLEET_URL.rstrip("/")
    if not base:
        raise ValueError("CHROMEFLEET_URL is not configured")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    return f"{ws_base}/cdp/{browser_id}"


async def _wait_for_cdp_websocket(ws_url: str, timeout_s: float = 120.0) -> None:
    """Poll the ChromeFleet CDP WebSocket proxy until the browser is reachable."""
    if not ws_url:
        raise TimeoutError("CDP WebSocket URL is empty or None")

    start = asyncio.get_event_loop().time()
    deadline = start + timeout_s
    last_error: Exception | None = None

    while asyncio.get_event_loop().time() < deadline:
        try:
            async with websockets.connect(ws_url, close_timeout=2):
                pass
            elapsed = asyncio.get_event_loop().time() - start
            logger.debug(f"CDP WebSocket is ready after {elapsed:.2f}s")
            return
        except Exception as e:
            last_error = e
            elapsed = asyncio.get_event_loop().time() - start
            logger.debug(f"CDP WebSocket not ready after {elapsed:.2f}s: {e}")
        await asyncio.sleep(0.5)

    raise TimeoutError(
        f"CDP WebSocket not ready at {ws_url} after {timeout_s}s (last_error={last_error})"
    )


async def _create_browser_from_websocket(ws_url: str, browser_id: str) -> zd.Browser:
    """Create a zendriver Browser connected via a CDP WebSocket URL.

    Uses the same approach as middleman's create_browser_from_cdp_websocket.
    """
    parsed = urlparse(ws_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 9222

    config = Config(host=host, port=port)
    instance = zd.Browser(config)
    instance._http = HTTPApi((host, port))  # type: ignore[attr-defined]

    try:
        instance.info = ContraDict(await instance._http.get("version"), silent=True)  # type: ignore[attr-defined]
    except Exception:
        instance.info = ContraDict({"webSocketDebuggerUrl": ws_url}, silent=True)

    instance.connection = Connection(ws_url, _owner=instance)

    if instance.config.autodiscover_targets:
        instance.connection.handlers[zd.cdp.target.TargetInfoChanged] = [  # type: ignore[index]
            instance._handle_target_update  # type: ignore[attr-defined]
        ]
        instance.connection.handlers[zd.cdp.target.TargetCreated] = [  # type: ignore[index]
            instance._handle_target_update  # type: ignore[attr-defined]
        ]
        instance.connection.handlers[zd.cdp.target.TargetDestroyed] = [  # type: ignore[index]
            instance._handle_target_update  # type: ignore[attr-defined]
        ]
        instance.connection.handlers[zd.cdp.target.TargetCrashed] = [  # type: ignore[index]
            instance._handle_target_update  # type: ignore[attr-defined]
        ]
        await instance.connection.send(zd.cdp.target.set_discover_targets(discover=True))

    await instance.update_targets()
    util.get_registered_instances().add(instance)

    instance.id = browser_id  # type: ignore[attr-defined]
    logger.info(f"Connected to ChromeFleet browser {browser_id} via WebSocket at {ws_url}")
    return instance


async def _call_chromefleet_api(method: HTTP_METHOD, browser_id: str) -> httpx.Response:
    base_url = settings.CHROMEFLEET_URL.rstrip("/")
    if not base_url:
        raise ValueError("CHROMEFLEET_URL is not configured")

    url = f"{base_url}/api/v1/browsers/{browser_id}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.request(method, url)
        response.raise_for_status()
        return response


async def get_remote_browser(browser_id: str) -> zd.Browser | None:
    """Find an existing ChromeFleet browser and connect via WebSocket."""
    logger.info(f"Finding the ChromeFleet browser: {browser_id}")
    try:
        response = await _call_chromefleet_api("GET", browser_id)
        if response.status_code != 200:
            return None
    except Exception:
        return None

    ws_url = _build_cdp_websocket_url(browser_id)
    await _wait_for_cdp_websocket(ws_url)
    browser = await _create_browser_from_websocket(ws_url, browser_id)
    return browser


async def create_remote_browser(browser_id: str) -> zd.Browser:
    """Start a remote Chrome via ChromeFleet and connect via CDP WebSocket proxy."""
    logger.info(f"Starting new ChromeFleet browser: {browser_id}")
    await _call_chromefleet_api("POST", browser_id)

    ws_url = _build_cdp_websocket_url(browser_id)
    await _wait_for_cdp_websocket(ws_url)
    browser = await _create_browser_from_websocket(ws_url, browser_id)
    return browser


async def terminate_remote_browser(browser: zd.Browser) -> None:
    """Terminate an existing remote Chrome via ChromeFleet."""
    browser_id = cast(str, browser.id)  # type: ignore[attr-defined]
    logger.info(f"Terminating ChromeFleet browser: {browser_id}")
    await _call_chromefleet_api("DELETE", browser_id)
    logger.info(f"Successfully terminated ChromeFleet browser: {browser_id}")
