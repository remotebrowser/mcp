"""Proxy configuration for browser sessions.

This module provides proxy configuration for external proxy service integration
with hierarchical location support (city, state, country) and multiple proxy types.
"""

import asyncio
from dataclasses import dataclass
from ipaddress import ip_address as parse_ip
from typing import Self
from urllib.parse import urlparse

import httpx
import zendriver as zd
from loguru import logger
from nanoid import generate
from pydantic import BaseModel, model_validator

from getgather.browser.proxy_builder import build_proxy_config
from getgather.config import settings
from getgather.request_info import RequestInfo

IP_CHECK_URL = "https://ip.fly.dev/ip"
MINIMUM_SPEED_MBPS = 25
BEST_OF_N_PROXY_NUMBER = 3
FRIENDLY_CHARS = "23456789abcdefghijkmnpqrstuvwxyz"

# Error patterns indicating location-specific failures
LOCATION_ERROR_PATTERNS = [
    "exit node not found",
    "no exit found",
    "location not available",
    "geo targeting",
    "invalid geo",
    "bad gateway",
    "status 502",
    "status 503",
    "status 504",
    " 502 ",
    " 503 ",
    " 504 ",
    "400 bad request",
]

# Error patterns indicating general proxy failures
PROXY_ERROR_PATTERNS = [
    "407",
    "proxy authentication required",
    "unauthorized",
    "invalid credentials",
    "connection refused",
    "connection reset",
]

# Valid US states (normalized with underscores)
VALID_US_STATES = {
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new_hampshire",
    "new_jersey",
    "new_mexico",
    "new_york",
    "north_carolina",
    "north_dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode_island",
    "south_carolina",
    "south_dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west_virginia",
    "wisconsin",
    "wyoming",
}


async def _set_proxy_url(
    browser_id: str, browser_proxy_url: str = settings.CHROMEFLEET_PROXY_URL
) -> None:
    proxy_url = browser_proxy_url.replace("{session_id}", browser_id)  # for now 1:1 is fine
    configure_url = (
        settings.CHROMEFLEET_URL.rstrip("/") + f"/api/v1/browsers/{browser_id}/configure"
    )
    logger.info(f"Configuring ChromeFleet browser proxy via: {configure_url}")
    async with httpx.AsyncClient() as client:
        resp = await client.post(configure_url, json={"proxy_url": proxy_url})
        resp.raise_for_status()


async def _check_browser_ip(page: zd.Tab) -> str | None:
    from getgather.zen_distill import zen_navigate_with_retry

    await zen_navigate_with_retry(page, IP_CHECK_URL, wait_for_ready=False)
    body = await page.select("body")
    ip_address = None
    if body:
        ip_address = body.text.strip()
        logger.info(f"Browser validated. IP address: {ip_address}")
    else:
        logger.info("Browser validated (could not extract IP)")

    return ip_address


async def change_and_validate_proxy(
    browser: zd.Browser, location: dict[str, str] | None = None
) -> None:
    from getgather.zen_distill import (
        get_new_page,
    )

    browser_id: str = str(browser.id)  # type: ignore
    page = await get_new_page(browser)
    original_ip = await _check_browser_ip(page)

    if location:
        validated_location = Location(**location)
        logger.info(f"Setting up location-based proxy for: {validated_location}")

        if (
            not settings.PROXY_USERNAME
            or not settings.PROXY_PASSWORD
            or not settings.PROXY_HOST_PORT
        ):
            raise ValueError(
                "Location-based proxy requires PROXY_USERNAME, PROXY_PASSWORD, and PROXY_HOST_PORT settings"
            )

        proxy_properties = await get_best_proxy(
            location=validated_location,
            proxy_username=settings.PROXY_USERNAME,
            proxy_password=settings.PROXY_PASSWORD,
            proxy_host_port=settings.PROXY_HOST_PORT,
            num_sessions=BEST_OF_N_PROXY_NUMBER,
        )

        logger.info(
            f"Configuring browser {browser_id} with validated proxy (IP: {proxy_properties.proxy_ip})"
        )
        await _set_proxy_url(browser_id, browser_proxy_url=proxy_properties.proxy_url)

    elif settings.CHROMEFLEET_PROXY_URL:
        await _set_proxy_url(browser_id, browser_proxy_url=settings.CHROMEFLEET_PROXY_URL)
    else:
        logger.warning(
            "IGNORING PROXY SETTING: Currently only proxy configuration by location or by explicit URL are allowed"
        )
        return

    new_ip = await _check_browser_ip(page)
    if original_ip == new_ip and original_ip is not None:
        logger.error(
            f"Proxy setup may have failed, IP address did not change after proxy configuration: {new_ip}"
        )
    else:
        logger.debug(f"Proxy setup successful, IP changed from {original_ip} to {new_ip}")


def mask_credentials(url: str) -> str:
    """Mask password in URL for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.username and parsed.password and parsed.hostname:
            masked = f"{parsed.username}:****@{parsed.hostname}"
            if parsed.port:
                masked += f":{parsed.port}"
            return parsed._replace(netloc=masked).geturl()
        return url
    except Exception:
        return url


class Location(BaseModel):
    """Location information for proxy configuration.

    Validation rules:
    - Country: Must be 2-char ISO code, normalized to lowercase
    - State: Normalized to lowercase with underscores, validated for US
    - Non-US countries: postal_code and state raise ValueError
    """

    country: str | None = None
    state: str | None = None
    city: str | None = None
    city_compacted: str | None = None
    postal_code: str | None = None

    @model_validator(mode="after")
    def validate_and_normalize(self) -> Self:
        self.country = (str(self.country) if self.country else "").lower().strip()
        self.state = (str(self.state) if self.state else "").lower().strip().replace(" ", "_")
        self.city = (str(self.city) if self.city else "").lower().strip().replace(" ", "_")
        self.postal_code = str(self.postal_code) if self.postal_code else None

        if not self.country or len(self.country) != 2 or not self.country.isalpha():
            raise ValueError(
                f"Invalid country code: '{self.country}'. Must be a 2-character ISO country code (e.g., 'us', 'uk')"
            )

        if self.country != "us":
            if self.postal_code:
                raise ValueError(
                    f"postal_code not supported for non-US (country: '{self.country}')"
                )
            if self.state:
                raise ValueError(f"state not supported for non-US (country: '{self.country}')")

        if self.country == "us" and self.state and self.state not in VALID_US_STATES:
            raise ValueError(f"Invalid US state: '{self.state}'")

        if self.city:
            self.city_compacted = (
                self.city.lower().replace("-", "").replace("_", "").replace(" ", "")
            )

        return self


class ProxyConfig(BaseModel):
    proxy_url: str | None = None
    location: Location | None = None


class ProxyProperties(BaseModel):
    """Properties of an upstream proxy"""

    proxy_url: str
    proxy_ip: str


def format_proxy_url_from_location(
    location: Location,
    proxy_session_id: str,
    proxy_username: str,
    proxy_password: str,
    proxy_host_port: str,
) -> str:
    """
    Args:
        location: Location object with some of country, state, city, postal_code
        proxy_session_id: Session ID for proxy authentication
        proxy_password: Password for proxy authentication
        proxy_username: Username for proxy authentication
    Returns:
        Formatted proxy URL with location placeholders replaced.
    For now, 1:1 mapping from browser id to proxy session id is ok.
    """
    username_template = f"customer-{proxy_username}"
    if location.country:
        username_template += f"-cc-{location.country}"
    if location.state:
        username_template += f"-st-us_{location.state}"
    if location.city_compacted:
        username_template += f"-city-{location.city_compacted}"
    if location.postal_code:
        username_template += f"-postalcode-{location.postal_code}"
    username_template += (
        f"-sessid-{proxy_session_id}-sesstime-1440"  # TODO can make sesstime configurable later
    )
    return f"http://{username_template}:{proxy_password}@{proxy_host_port}"


class ValidationResult(BaseModel):
    """Result of proxy validation. This makes batching and logic easier than multiple exception handling."""

    success: bool
    proxy_url: str | None = None
    ip_address: str | None = None
    error: str | None = None
    is_location_error: bool = False


def _is_location_error(error_text: str) -> bool:
    """Check if error indicates location-specific failure."""
    lower = error_text.lower()
    return any(p in lower for p in LOCATION_ERROR_PATTERNS)


def _is_fatal_proxy_error(error_text: str) -> bool:
    """Check if error indicates fatal proxy failure (don't retry)."""
    lower = error_text.lower()
    return any(p in lower for p in PROXY_ERROR_PATTERNS)


@dataclass
class _RequestOutcome:
    """Result of a single validation request attempt."""

    success: bool
    ip_address: str | None = None
    error: str | None = None
    is_location_error: bool = False
    should_retry: bool = True


async def _make_request(client: httpx.AsyncClient) -> _RequestOutcome:
    """Make a single validation request through the proxy.

    Returns an outcome indicating success, or failure with retry guidance.
    """
    try:
        response = await client.get(IP_CHECK_URL)
        response.raise_for_status()

        ip_str = response.text.strip()
        parsed_ip = parse_ip(ip_str)
        return _RequestOutcome(success=True, ip_address=str(parsed_ip))

    except ValueError:
        return _RequestOutcome(
            success=False,
            error="Invalid IP format in response",
            should_retry=True,
        )

    except httpx.ProxyError as e:
        error = str(e)
        is_fatal = _is_fatal_proxy_error(error)
        return _RequestOutcome(
            success=False,
            error=error,
            is_location_error=_is_location_error(error),
            should_retry=not is_fatal,
        )

    except httpx.TimeoutException:
        return _RequestOutcome(
            success=False,
            error="Request timed out",
            should_retry=True,
        )

    except httpx.HTTPStatusError as e:
        error = f"HTTP {e.response.status_code}"
        return _RequestOutcome(
            success=False,
            error=error,
            is_location_error=_is_location_error(error),
            should_retry=True,
        )

    except Exception as e:
        return _RequestOutcome(
            success=False,
            error=f"{type(e).__name__}: {e}",
            should_retry=True,
        )


async def _validate_proxy_connection(
    proxy_url: str,
    *,
    max_retries: int = 3,
    timeout: int = 10,
    backoff: float = 0.5,
) -> ValidationResult:
    """Validate proxy by making HTTP request through it.

    Makes a request to checkip.amazonaws.com through the proxy.
    Retries transient failures up to max_retries times.

    Args:
        proxy_url: Full proxy URL with credentials
            e.g., "http://user:pass@proxy.com:7777"
        max_retries: Maximum number of attempts
        timeout: Request timeout in seconds
        backoff: Seconds to wait between retries

    Returns:
        ValidationResult with success status, IP address, or error details.
    """
    masked_url = mask_credentials(proxy_url)
    logger.info(f"Validating proxy: {masked_url}")

    last_outcome: _RequestOutcome | None = None

    async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
        for attempt in range(1, max_retries + 1):
            logger.debug(f"Validation attempt {attempt}/{max_retries}")

            outcome = await _make_request(client)
            last_outcome = outcome

            if outcome.success:
                logger.info(f"Proxy validated, IP: {outcome.ip_address}")
                return ValidationResult(
                    success=True,
                    proxy_url=proxy_url,
                    ip_address=outcome.ip_address,
                )

            if not outcome.should_retry:
                logger.error(f"Fatal proxy error: {outcome.error}")
                return ValidationResult(
                    success=False,
                    proxy_url=proxy_url,
                    error=outcome.error,
                    is_location_error=outcome.is_location_error,
                )

            logger.debug(f"Attempt {attempt} failed: {outcome.error}")

            if attempt < max_retries:
                await asyncio.sleep(backoff)

    error_msg = f"Validation failed after {max_retries} attempts: {last_outcome.error if last_outcome else 'unknown'}"
    logger.error(error_msg)

    return ValidationResult(
        success=False,
        proxy_url=proxy_url,
        error=error_msg,
        is_location_error=last_outcome.is_location_error if last_outcome else False,
    )


async def _try_proxy_session_id(
    location: Location,
    proxy_session_id: str,
    proxy_username: str,
    proxy_password: str,
    proxy_host_port: str,
) -> ProxyProperties:
    """Try to validate a single proxy session ID.

    Args:
        location: Location to target
        proxy_session_id: Session ID to try
        proxy_username: Proxy username
        proxy_password: Proxy password
        proxy_host_port: Proxy host:port

    Returns:
        ProxyProperties if successful

    Raises:
        RuntimeError: If validation fails
    """
    proxy_url = format_proxy_url_from_location(
        location, proxy_session_id, proxy_username, proxy_password, proxy_host_port
    )
    masked_url = mask_credentials(proxy_url)
    logger.debug(f"Trying proxy session {proxy_session_id}: {masked_url}")

    validation_result = await _validate_proxy_connection(proxy_url)
    if not validation_result.success:
        error_msg = f"(not critical) Proxy Session {proxy_session_id} connection validation failed : {validation_result.error}"
        logger.warning(error_msg)
        raise RuntimeError(error_msg)

    """ TODO: 
        Create a (throwaway) browser and receive a page. 
        Configure said browser with the proxy of interest. 
        Test the speed (and potentially brand connectivity).
        Destroy the throwaway browser after validation.

        Open question where we want this type of validation to live. Could be here or could be on recognition of error with the distillation code requesting new proxy.
        speed_result = await _validate_proxy_speed(page)
    """

    if validation_result.proxy_url and validation_result.ip_address:
        logger.info(
            f"Session {proxy_session_id} validated successfully, IP: {validation_result.ip_address}"
        )
        return ProxyProperties(
            proxy_url=validation_result.proxy_url, proxy_ip=validation_result.ip_address
        )

    raise RuntimeError(f"Session {proxy_session_id}: proxy_url and IP cannot be None")


async def get_best_proxy(
    location: Location,
    proxy_username: str,
    proxy_password: str,
    proxy_host_port: str,
    num_sessions: int = BEST_OF_N_PROXY_NUMBER,
) -> ProxyProperties:
    """Try multiple proxy session IDs in parallel and return the first successful one.

    Args:
        location: Target location for proxy
        proxy_username: Proxy username
        proxy_password: Proxy password
        proxy_host_port: Proxy host:port
        num_sessions: Number of session IDs to try in parallel (default: 5)

    Returns:
        ProxyProperties of the first successful proxy

    Raises:
        RuntimeError: If all session attempts fail
    """

    # NOTE: in the future, we may need to either store or generate these ids in a different way for more persistent cases
    # We also will do the location hierarchy via scoring (more granular location -> higher score) and take the highest score
    session_ids = [generate(FRIENDLY_CHARS) for _ in range(num_sessions)]
    logger.info(f"Trying {num_sessions} proxy sessions in parallel for location: {location}")

    tasks = [
        _try_proxy_session_id(location, session_id, proxy_username, proxy_password, proxy_host_port)
        for session_id in session_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, ProxyProperties):
            logger.info(f"Successfully validated proxy session {session_ids[i]}")
            return result
        else:
            logger.debug(f"Session {session_ids[i]} failed: {result}")

    error_msg = f"All {num_sessions} proxy session attempts failed for location {location}"
    logger.error(error_msg)
    raise RuntimeError(error_msg)


########### TODO Migrate away from below system ################


async def setup_proxy(
    profile_id: str, request_info: RequestInfo | None = None
) -> dict[str, str] | None:
    """Setup proxy configuration using the proxy type system.

    Proxy types are configured via PROXY_* environment variables:
    - proxy-1: First configured proxy (from PROXY_1_*)
    - proxy-2: Second configured proxy (from PROXY_2_*)
    - etc.

    Proxy type can be specified via:
    1. x-proxy-type header (highest priority)
    2. DEFAULT_PROXY_TYPE environment variable (fallback)
    3. No proxy if neither is set

    Args:
        profile_id: Profile ID to use as base proxy username
        request_info: Optional request information containing location data and proxy type

    Returns:
        dict: Proxy configuration with server, username and password
        None: If no proxy is configured or proxy-0 (no proxy) is selected
    """
    # Determine which proxy type to use
    proxy_type = None

    # Priority 1: Check if request_info specifies a proxy type via header
    if request_info and request_info.proxy_type:
        proxy_type = request_info.proxy_type
        logger.info(f"Proxy type from header: {proxy_type}")
    # Priority 2: Use DEFAULT_PROXY_TYPE if configured
    elif settings.DEFAULT_PROXY_TYPE:
        proxy_type = settings.DEFAULT_PROXY_TYPE
        logger.info(f"Using default proxy type: {proxy_type}")
    else:
        logger.info("No proxy type specified (no header or DEFAULT_PROXY_TYPE)")
        return None

    # Load proxy configurations
    proxy_configs = settings.proxy_configs

    if proxy_type not in proxy_configs:
        logger.warning(
            f"Proxy type '{proxy_type}' not found in configuration. "
            f"Available types: {list(proxy_configs.keys())}"
        )
        return None

    proxy_config = proxy_configs[proxy_type]

    # Build proxy configuration with dynamic parameters (profile_id as session)
    result = build_proxy_config(proxy_config, profile_id, request_info)

    # Log the final proxy configuration for debugging
    if result:
        # Mask password in server URL for logging
        server = result.get("server", "")
        import re

        masked_server = re.sub(r":([^:@]+)@", r":***@", server)

        if "username" in result:
            logger.info(
                f"✓ Proxy configured: type={proxy_type}, "
                f"server={masked_server}, username={result['username']}"
            )
        else:
            logger.info(f"✓ Proxy configured: type={proxy_type}, server={masked_server}")
    else:
        logger.info(f"✓ No proxy configured (type={proxy_type} returned None)")

    return result
