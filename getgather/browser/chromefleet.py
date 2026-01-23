import asyncio
import urllib.parse

import httpx
import zendriver as zd

from getgather.browser.page import get_new_page, zen_navigate_with_retry
from getgather.config import settings
from getgather.logs import logger


def _format_host_for_cdp(host: str) -> str:
    """Ensure IPv6 hosts are wrapped in brackets for HTTP/CDP URLs."""
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _strip_brackets(host: str) -> str:
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def _parse_cdp_endpoint(cdp_url: str) -> tuple[str, int]:
    """Parse host/port from a CDP URL, handling IPv6."""
    parsed: httpx.URL | None = None
    parse_error: Exception | None = None
    try:
        parsed = httpx.URL(cdp_url)
    except Exception as e:
        parse_error = e

    split = urllib.parse.urlsplit(cdp_url)

    host = parsed.host if parsed else None
    port: int | None = parsed.port if parsed else None

    # Fallback to stdlib parsing when httpx fails or host is blank
    if not host:
        host = split.hostname or split.netloc
    if port is None:
        try:
            port = split.port
        except ValueError:
            port = None

    # Handle IPv6 without brackets that confuses parsers (netloc has many colons).
    if split.netloc and ":" in split.netloc:
        host_part, _, port_part = split.netloc.rpartition(":")
        if host_part:
            try:
                int_port = int(port_part)
                port = port or int_port
            except ValueError:
                pass
            if ":" in host_part or not host:
                host = host_part

    host = host or ""
    if not host.strip("[] ") or host.startswith(":"):
        detail = f"; parse_error={parse_error}" if parse_error else ""
        raise ValueError(f"Invalid CDP URL returned from ChromeFleet: {cdp_url}{detail}")

    return _format_host_for_cdp(host), port or 9222


async def _validated_cdp_url(
    browser_id: str, endpoint: str, attempts: int = 3, delay_s: float = 1.0
) -> tuple[str, str, int]:
    """
    Fetch and validate a CDP URL from ChromeFleet, retrying if the URL is malformed/empty.

    Returns:
        tuple of (cdp_url, host, port)
    """

    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        response = await _call_chromefleet_api(endpoint, browser_id)
        data = response.json()
        cdp_url = data.get("cdp_url")
        try:
            host, port = _parse_cdp_endpoint(cdp_url or "")
            logger.info(
                "ChromeFleet %s returned cdp_url=%s host=%s port=%s",
                endpoint,
                cdp_url,
                host,
                port,
                extra={"browser_id_id": browser_id},
            )
            return cdp_url, host, port
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Invalid cdp_url from ChromeFleet (attempt %s/%s): %s",
                attempt,
                attempts,
                cdp_url,
                extra={"browser_id_id": browser_id},
            )
            if attempt < attempts:
                await asyncio.sleep(delay_s)
                # After the initial start, query is the most up-to-date source.
                endpoint = "query"

    raise ValueError(
        f"ChromeFleet returned invalid cdp_url after {attempts} attempts for browser_id={browser_id}: {last_error}"
    )


async def _wait_for_cdp(host: str, port: int, timeout_s: float = 60.0) -> None:
    formatted_host = _format_host_for_cdp(host)
    host_for_url = _strip_brackets(formatted_host)
    url = httpx.URL(scheme="http", host=host_for_url, port=port, path="/json/list")
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
            except Exception as r:
                last_error = r
                logger.warning(
                    f"CDP not ready after {asyncio.get_event_loop().time() - start_time:.2f}s, exception occurred: {r}"
                )
                pass
            await asyncio.sleep(0.25)
    raise TimeoutError(f"CDP not ready at {url} after {timeout_s}s (last_error={last_error})")


async def _connect_over_cdp(
    browser_id: str, cdp_url: str, host_override: str | None = None, port_override: int | None = None
) -> zd.Browser:
    """
    Connect to an existing Chrome instance over CDP.
    """
    host, port = _parse_cdp_endpoint(cdp_url)
    if host_override:
        host = host_override
    if port_override:
        port = port_override
    wait_timeout = 60.0

    logger.info(
        f"Connecting to ChromeFleet browser {browser_id} at {host}:{port} (cdp_url={cdp_url})",
        extra={"browser_id_id": browser_id},
    )

    browser_args = [
        "--start-maximized",
        "--no-dbus",  # avoids chromium probing real DBus sockets inside the container which are not needed
        "--proxy-server=http://127.0.0.1:8119",
    ]
    try:
        await _wait_for_cdp(host=host, port=port, timeout_s=wait_timeout)
    except TimeoutError as e:
        logger.warning(
            "Initial CDP wait timed out; re-querying ChromeFleet for %s",
            browser_id,
            extra={"browser_id_id": browser_id},
        )
        try:
            refreshed = await _call_chromefleet_api("query", browser_id)
            refreshed_url = refreshed.json().get("cdp_url")
            if refreshed_url and refreshed_url != cdp_url:
                host, port = _parse_cdp_endpoint(refreshed_url)
                cdp_url = refreshed_url
                logger.info(
                    "Received updated cdp_url=%s host=%s port=%s; retrying CDP wait",
                    cdp_url,
                    host,
                    port,
                    extra={"browser_id_id": browser_id},
                )
            await _wait_for_cdp(host=host, port=port, timeout_s=wait_timeout)
        except Exception:
            # Preserve original timeout context for clarity upstream
            raise e
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
    cdp_url, host, port = await _validated_cdp_url(browser_id, endpoint="start")

    browser = await _connect_over_cdp(
        browser_id, cdp_url, host_override=host, port_override=port
    )
    await _check_browser(browser)
    return browser


async def get_remote_browser(browser_id: str) -> zd.Browser:
    """
    Get an existing remote Chrome via ChromeFleet.
    The browser must already exist.
    """
    logger.info(f"Getting existing ChromeFleet browser: {browser_id}")
    cdp_url, host, port = await _validated_cdp_url(browser_id, endpoint="query")

    browser = await _connect_over_cdp(
        browser_id, cdp_url, host_override=host, port_override=port
    )
    await _check_browser(browser)
    return browser


async def terminate_remote_browser(browser_id: str) -> None:
    """Terminate an existing remote Chrome via ChromeFleet."""
    logger.info(f"Terminating ChromeFleet browser: {browser_id}")
    await _call_chromefleet_api("stop", browser_id)
    logger.info(f"Successfully terminated ChromeFleet browser: {browser_id}")
