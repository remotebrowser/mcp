import asyncio
from typing import Literal, cast
from urllib.parse import urlparse

import httpx
import zendriver as zd
from loguru import logger

from getgather.config import settings

HTTP_METHOD = Literal["GET", "POST", "DELETE"]


async def _wait_for_cdp(url: str, timeout_s: float = 60.0) -> None:
    start_time = asyncio.get_event_loop().time()
    deadline = start_time + timeout_s
    last_error: Exception | None = None
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                r = await client.get(url, timeout=2.0)
                if r.status_code == 200:
                    logger.debug(
                        f"CDP is ready after {asyncio.get_event_loop().time() - start_time:.2f}s"
                    )
                    return
                logger.debug(f"CDP not ready, status code: {r.status_code}")
            except Exception as e:
                last_error = e
                logger.warning(
                    f"CDP not ready after {asyncio.get_event_loop().time() - start_time:.2f}s, exception occurred: {e}"
                )
                pass
            await asyncio.sleep(0.25)
    raise TimeoutError(f"CDP not ready at {url} after {timeout_s}s (last_error={last_error})")


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
    logger.info(f"Finding the ChromeFleet browser: {browser_id}")
    try:
        response = await _call_chromefleet_api("GET", browser_id)
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception:
        return None

    cdp_url = data.get("cdp_url")
    await _wait_for_cdp(cdp_url, timeout_s=120.0)
    cdp = urlparse(cdp_url)  # type: ignore[assignment]
    hostname = cdp.hostname  # type: ignore[assignment]
    port = cdp.port  # type: ignore[assignment]
    assert hostname is not None
    assert port is not None
    logger.debug(f"Connecting to ChromeFleet CDP at {hostname}:{port}")
    # add '[' and ']' for ipv6 address
    cdp_hostname = f"[{hostname}]" if ":" in hostname and "[" not in hostname else hostname  # type: ignore[assignment]
    browser = await zd.Browser.create(host=cdp_hostname, port=port)  # type: ignore[arg-type]
    browser.id = browser_id  # type: ignore[attr-defined]
    return browser


async def create_remote_browser(browser_id: str) -> zd.Browser:
    """
    Start a remote Chrome via ChromeFleet and connect via CDP.
    The browser_id must not already be in use.
    """
    logger.info(f"Starting new ChromeFleet browser: {browser_id}")
    response = await _call_chromefleet_api("POST", browser_id)
    data = response.json()
    cdp_url = data.get("cdp_url")
    await _wait_for_cdp(cdp_url, timeout_s=120.0)

    cdp = urlparse(cdp_url)  # type: ignore[assignment]
    hostname = cdp.hostname  # type: ignore[assignment]
    port = cdp.port  # type: ignore[assignment]
    assert hostname is not None
    assert port is not None
    logger.debug(f"Connecting to ChromeFleet CDP at {hostname}:{port}")
    # add '[' and ']' for ipv6 address
    cdp_hostname = f"[{hostname}]" if ":" in hostname and "[" not in hostname else hostname  # type: ignore[assignment]
    browser = await zd.Browser.create(host=cdp_hostname, port=port)  # type: ignore[arg-type]
    browser.id = browser_id  # type: ignore[attr-defined]
    return browser


async def terminate_remote_browser(browser: zd.Browser) -> None:
    """Terminate an existing remote Chrome via ChromeFleet."""
    browser_id = cast(str, browser.id)  # type: ignore[attr-defined]
    logger.info(f"Terminating ChromeFleet browser: {browser_id}")
    await _call_chromefleet_api("DELETE", browser_id)
    logger.info(f"Successfully terminated ChromeFleet browser: {browser_id}")
