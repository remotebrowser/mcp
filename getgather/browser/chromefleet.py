import asyncio
import urllib.parse

import httpx
import zendriver as zd

from getgather.browser.page import get_new_page, zen_navigate_with_retry
from getgather.config import settings
from getgather.logs import logger


async def _wait_for_cdp(host: str, port: int, timeout_s: float = 30.0) -> None:
    url = f"http://{host}:{port}/json/list"
    start_time = asyncio.get_event_loop().time()
    deadline = start_time + timeout_s
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
            except Exception as r:
                logger.warning(
                    f"CDP not ready after {asyncio.get_event_loop().time() - start_time:.2f}s, exception occurred: {r}"
                )
                pass
            await asyncio.sleep(0.25)
    raise TimeoutError(f"CDP not ready at {url} after {timeout_s}s")


async def _connect_over_cdp(browser_id: str, cdp_url: str) -> zd.Browser:
    """
    Connect to an existing Chrome instance over CDP.
    """
    parsed = urllib.parse.urlparse(cdp_url)
    host: str = str(parsed.hostname) if parsed.hostname else "localhost"
    port: int = int(parsed.port) if parsed.port else 9222

    logger.info(
        f"Connecting to ChromeFleet browser {browser_id} at {host}:{port}",
        extra={"browser_id_id": browser_id},
    )

    browser_args = [
        "--start-maximized",
        "--no-dbus",  # avoids chromium probing real DBus sockets inside the container which are not needed
        "--proxy-server=http://127.0.0.1:8119",
    ]
    await _wait_for_cdp(host=host, port=port)
    browser = await zd.Browser.create(
        host=host, port=port, sandbox=False, browser_args=browser_args
    )
    browser.id = browser_id  # type: ignore[attr-defined]
    return browser


async def _check_browser(browser: zd.Browser) -> None:
    """
    Check if the given browser is responsive.
    """
    MAX_ATTEMPTS = 3
    IP_CHECK_URL = "https://ip.fly.dev/ip"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        logger.info(
            f"Checking browser (attempt {attempt}/{MAX_ATTEMPTS})...",
            extra={"browser_id": browser.id},  # type: ignore[attr-defined]
        )

        try:
            logger.info(f"Validating browser at {IP_CHECK_URL}...")
            page = await get_new_page(browser)
            # Skip wait_for_ready_state for IP check - ip.fly.dev is a simple text page
            await zen_navigate_with_retry(page, IP_CHECK_URL, wait_for_ready=False)
            body = await page.select("body")
            if body:
                ip_address = body.text.strip()
                logger.info(f"Browser validated. IP address: {ip_address}")
            else:
                logger.info("Browser validated (could not extract IP)")
            return
        except Exception as e:
            logger.warning(f"Browser validation failed on attempt {attempt}: {e}")
        await asyncio.sleep(1.0)

    logger.error(
        f"Failed to get a working browser after {MAX_ATTEMPTS} attempts!",
        extra={"browser_id": browser.id},  # type: ignore[attr-defined]
    )
    raise RuntimeError(f"Failed to get a working Zendriver browser after {MAX_ATTEMPTS} attempts!")


async def _call_chromefleet_api(endpoint: str, browser_id: str) -> httpx.Response:
    """
    Helper to call the ChromeFleet API.

    Args:
        endpoint: The API endpoint (e.g., 'start', 'query', 'stop')
        browser_id: The browser ID to use in the endpoint

    Returns:
        The HTTP response
    """
    base_url = settings.CHROMEFLEET_URL.rstrip("/")
    if not base_url:
        raise ValueError("CHROMEFLEET_URL is not configured")

    url = f"{base_url}/api/v1/{endpoint}/{browser_id}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response


async def create_remote_browser(browser_id: str) -> zd.Browser:
    """
    Start a remote Chrome via ChromeFleet and connect via CDP.
    The browser_id must not already be in use.
    """
    logger.info(f"Starting new ChromeFleet browser: {browser_id}")
    response = await _call_chromefleet_api("start", browser_id)
    data = response.json()
    cdp_url = data["cdp_url"]

    browser = await _connect_over_cdp(browser_id, cdp_url)
    await _check_browser(browser)
    return browser


async def get_remote_browser(browser_id: str) -> zd.Browser:
    """
    Get an existing remote Chrome via ChromeFleet.
    The browser must already exist.
    """
    logger.info(f"Getting existing ChromeFleet browser: {browser_id}")
    response = await _call_chromefleet_api("query", browser_id)
    data = response.json()
    cdp_url = data["cdp_url"]

    browser = await _connect_over_cdp(browser_id, cdp_url)
    await _check_browser(browser)
    return browser


async def terminate_remote_browser(browser_id: str) -> None:
    """Terminate an existing remote Chrome via ChromeFleet."""
    logger.info(f"Terminating ChromeFleet browser: {browser_id}")
    await _call_chromefleet_api("stop", browser_id)
    logger.info(f"Successfully terminated ChromeFleet browser: {browser_id}")
