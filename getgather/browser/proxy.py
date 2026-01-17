"""Proxy configuration for browser sessions.

This module provides proxy configuration for external proxy service integration
with hierarchical location support (city, state, country) and multiple proxy types.
"""

from getgather.browser.proxy_builder import build_proxy_config
from getgather.config import settings
from getgather.logs import logger
from getgather.request_info import RequestInfo


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
