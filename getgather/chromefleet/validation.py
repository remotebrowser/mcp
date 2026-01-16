"""Proxy validation module for HTTP and CDP testing.

This module provides functionality to validate proxy configurations by testing:
1. HTTP validation: Request through proxy to get external IP
2. CDP validation: Connect to browser via CDP and navigate to test page
"""

import asyncio
from ipaddress import ip_address as parse_ip
from urllib.parse import urlparse

import httpx
from loguru import logger
from pydantic import IPvAnyAddress

from getgather.chromefleet.models import ProxyValidationResult

logger = logger.bind(topic="chromefleet_validation")

# HTTP validation settings
IP_CHECK_URL = "http://checkip.amazonaws.com"
HTTP_VALIDATION_TIMEOUT = 10  # seconds
MAX_HTTP_RETRIES = 3
RETRY_BACKOFF_SECONDS = 0.5

# CDP validation settings
CDP_VALIDATION_URL = "https://ip.fly.dev/ip"
CDP_VALIDATION_TIMEOUT = 30  # seconds (as specified in requirements)

# Error patterns that indicate location-specific failures.
# If these appear, we should try the next location in hierarchy rather than failing.
LOCATION_ERROR_PATTERNS: list[str] = [
    # Provider messages about missing geo-nodes
    "exit node not found",
    "no exit found",
    "location not available",
    "geo targeting",
    "invalid geo",
    # Gateway/upstream failures often tied to specific exit nodes
    "bad gateway",
    "status 502",
    "status 503",
    "status 504",
    "status 522",
    " 502 ",
    " 503 ",
    " 504 ",
    " 522 ",
    # Invalid geo parameters
    "400 bad request",
]

# Error patterns that indicate general proxy failures (not location-specific).
# These should NOT trigger location fallback - fail immediately.
PROXY_ERROR_PATTERNS: list[str] = [
    # Authentication errors
    "407",
    "proxy authentication required",
    "unauthorized",
    "invalid credentials",
    # Connection errors
    "connection refused",
    "connection reset",
    "network unreachable",
]


def is_location_error(error_text: str) -> bool:
    """Check if an error indicates a location-specific failure.

    Location errors should trigger fallback to next hierarchy level.

    Args:
        error_text: Error message to check

    Returns:
        True if the error is location-specific
    """
    error_lower = error_text.lower()
    return any(pattern in error_lower for pattern in LOCATION_ERROR_PATTERNS)


def is_proxy_error(error_text: str) -> bool:
    """Check if an error indicates a general proxy failure.

    Proxy errors should NOT trigger location fallback - fail immediately.

    Args:
        error_text: Error message to check

    Returns:
        True if the error is a general proxy failure
    """
    error_lower = error_text.lower()
    return any(pattern in error_lower for pattern in PROXY_ERROR_PATTERNS)


def mask_credentials(url: str) -> str:
    """Mask credentials in URL for safe logging.

    Args:
        url: URL potentially containing credentials

    Returns:
        URL with password masked as ****

    Example:
        >>> mask_credentials("http://user:pass@proxy.com:8889")
        'http://user:****@proxy.com:8889'
    """
    try:
        parsed = urlparse(url)
        if parsed.username and parsed.password and parsed.hostname:
            masked_netloc = f"{parsed.username}:****@{parsed.hostname}"
            if parsed.port:
                masked_netloc += f":{parsed.port}"
            return parsed._replace(netloc=masked_netloc).geturl()
        return url
    except Exception:
        return url


async def validate_proxy_http(proxy_url: str) -> ProxyValidationResult:
    """Validate proxy by fetching external IP via HTTP.

    Makes a request through the proxy to checkip.amazonaws.com to verify:
    1. Proxy connection works
    2. We can get a valid IP address through it

    Args:
        proxy_url: Full proxy URL with credentials
            (e.g., "http://user:pass@proxy.oxylabs.io:7777")

    Returns:
        ProxyValidationResult with success status, IP address, error message,
        and is_location_error flag indicating if fallback should be attempted.
    """
    masked_url = mask_credentials(proxy_url)
    last_error: str = ""
    last_is_location_error: bool = False

    async with httpx.AsyncClient(
        proxy=proxy_url,
        timeout=HTTP_VALIDATION_TIMEOUT,
    ) as client:
        for attempt in range(1, MAX_HTTP_RETRIES + 1):
            try:
                logger.debug(
                    f"HTTP validation attempt {attempt}/{MAX_HTTP_RETRIES}",
                    proxy_url=masked_url,
                )

                response = await client.get(IP_CHECK_URL)
                response.raise_for_status()

                ip_str = response.text.strip()

                # Validate it's actually an IP address
                try:
                    validated_ip = parse_ip(ip_str)
                    result = ProxyValidationResult(
                        success=True,
                        ip_address=validated_ip,
                    )
                    logger.info(
                        "HTTP proxy validation succeeded",
                        attempt=attempt,
                        ip=str(result.ip_address),
                        proxy_url=masked_url,
                    )
                    return result
                except ValueError as e:
                    last_error = f"Invalid IP format: {ip_str}"
                    last_is_location_error = False
                    logger.warning(
                        "Invalid IP format received",
                        ip=ip_str,
                        error=str(e),
                        proxy_url=masked_url,
                    )

            except httpx.TimeoutException as e:
                last_error = f"Timeout: {e}"
                last_is_location_error = is_location_error(str(e))
                logger.warning(
                    "HTTP validation timeout",
                    attempt=attempt,
                    error=str(e),
                    is_location_error=last_is_location_error,
                    proxy_url=masked_url,
                )

            except httpx.ProxyError as e:
                last_error = f"Proxy error: {e}"
                last_is_location_error = is_location_error(str(e))
                # If it's a general proxy error, don't retry - fail fast
                if is_proxy_error(str(e)):
                    logger.error(
                        "Proxy authentication/connection error - not retrying",
                        attempt=attempt,
                        error=str(e),
                        proxy_url=masked_url,
                    )
                    return ProxyValidationResult(
                        success=False,
                        error=last_error,
                        is_location_error=False,
                    )
                logger.warning(
                    "Proxy connection error",
                    attempt=attempt,
                    error=str(e),
                    is_location_error=last_is_location_error,
                    proxy_url=masked_url,
                )

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e}"
                response_text = str(e)
                last_is_location_error = is_location_error(response_text)
                logger.warning(
                    "HTTP error during validation",
                    attempt=attempt,
                    status_code=e.response.status_code,
                    error=str(e),
                    is_location_error=last_is_location_error,
                    proxy_url=masked_url,
                )

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                last_is_location_error = is_location_error(str(e))
                logger.warning(
                    "Unexpected error during HTTP validation",
                    attempt=attempt,
                    error=str(e),
                    error_type=type(e).__name__,
                    is_location_error=last_is_location_error,
                    proxy_url=masked_url,
                )

            # Brief delay between retries (except on last attempt)
            if attempt < MAX_HTTP_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)

    error_msg = f"HTTP validation failed after {MAX_HTTP_RETRIES} attempts: {last_error}"
    logger.error(
        "HTTP proxy validation failed",
        error=error_msg,
        is_location_error=last_is_location_error,
        proxy_url=masked_url,
    )
    return ProxyValidationResult(
        success=False,
        error=error_msg,
        is_location_error=last_is_location_error,
    )


async def validate_proxy_cdp(cdp_url: str) -> ProxyValidationResult:
    """Validate proxy by connecting to browser via CDP and navigating to test page.

    Uses patchright to:
    1. Connect to the remote CDP URL
    2. Create a page and navigate to ip.fly.dev/ip
    3. Extract and validate the displayed IP

    Args:
        cdp_url: Chrome DevTools Protocol URL
            (e.g., "http://100.64.1.5:9222")

    Returns:
        ProxyValidationResult with success status, IP address, and error info.
    """
    try:
        from patchright.async_api import async_playwright
    except ImportError as e:
        logger.error("patchright not available for CDP validation", error=str(e))
        return ProxyValidationResult(
            success=False,
            error="patchright library not available",
            is_location_error=False,
        )

    logger.info("Starting CDP validation", cdp_url=cdp_url)

    try:
        async with async_playwright() as p:
            # Connect to existing browser via CDP
            browser = await asyncio.wait_for(
                p.chromium.connect_over_cdp(cdp_url),
                timeout=CDP_VALIDATION_TIMEOUT,
            )

            try:
                # Get the default context or create one
                contexts = browser.contexts
                if contexts:
                    context = contexts[0]
                else:
                    context = await browser.new_context()

                # Create a new page
                page = await context.new_page()

                try:
                    # Navigate to IP check page
                    logger.debug("Navigating to IP check page", url=CDP_VALIDATION_URL)
                    await page.goto(
                        CDP_VALIDATION_URL,
                        timeout=CDP_VALIDATION_TIMEOUT * 1000,  # patchright uses ms
                        wait_until="domcontentloaded",
                    )

                    # Get the page content (should be just the IP)
                    content = await page.content()
                    # Extract text from body
                    ip_text = await page.evaluate("document.body.innerText")
                    ip_str = ip_text.strip()

                    logger.debug("CDP page content retrieved", ip_text=ip_str)

                    # Validate IP format
                    try:
                        validated_ip: IPvAnyAddress = parse_ip(ip_str)
                        logger.info(
                            "CDP proxy validation succeeded",
                            ip=str(validated_ip),
                            cdp_url=cdp_url,
                        )
                        return ProxyValidationResult(
                            success=True,
                            ip_address=validated_ip,
                        )
                    except ValueError:
                        # Try to extract IP from HTML if direct text didn't work
                        import re

                        ip_match = re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", content)
                        if ip_match:
                            ip_str = ip_match.group(1)
                            validated_ip = parse_ip(ip_str)
                            logger.info(
                                "CDP proxy validation succeeded (extracted from HTML)",
                                ip=str(validated_ip),
                                cdp_url=cdp_url,
                            )
                            return ProxyValidationResult(
                                success=True,
                                ip_address=validated_ip,
                            )

                        error_msg = f"Could not extract valid IP from page: {ip_text[:100]}"
                        logger.error(error_msg, cdp_url=cdp_url)
                        return ProxyValidationResult(
                            success=False,
                            error=error_msg,
                            is_location_error=False,
                        )

                finally:
                    await page.close()

            finally:
                # Don't close the browser - it's managed by ChromeFleet
                pass

    except asyncio.TimeoutError:
        error_msg = f"CDP validation timed out after {CDP_VALIDATION_TIMEOUT}s"
        logger.error(error_msg, cdp_url=cdp_url)
        return ProxyValidationResult(
            success=False,
            error=error_msg,
            is_location_error=is_location_error(error_msg),
        )

    except Exception as e:
        error_msg = f"CDP validation failed: {type(e).__name__}: {e}"
        logger.error(
            "CDP validation failed",
            error=str(e),
            error_type=type(e).__name__,
            cdp_url=cdp_url,
        )
        return ProxyValidationResult(
            success=False,
            error=error_msg,
            is_location_error=is_location_error(str(e)),
        )
