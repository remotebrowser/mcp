"""MCP tools for ChromeFleet proxy configuration.

This module provides MCP tools for configuring and managing ChromeFleet
proxy containers through the Model Context Protocol.
"""

import uuid
from typing import Any

from loguru import logger

from getgather.chromefleet import (
    Location,
    ProxyConfigurationError,
    ProxyConfigurator,
)
from getgather.chromefleet.proxy_configurator import stop_proxy_container
from getgather.config import settings
from getgather.mcp.registry import GatherMCP

logger = logger.bind(topic="chromefleet_mcp")

# Create the MCP instance - will be auto-discovered
chromefleet_mcp = GatherMCP(brand_id="chromefleet", name="ChromeFleet Proxy MCP")


@chromefleet_mcp.tool
async def configure_proxy(
    country: str | None = None,
    state: str | None = None,
    city: str | None = None,
    postal_code: str | None = None,
) -> dict[str, Any]:
    """Configure a geo-targeted proxy through ChromeFleet.

    This tool starts a ChromeFleet container with a configured residential proxy
    targeting the specified location. The proxy is validated via both HTTP and
    CDP to ensure it's working correctly.

    Args:
        country: 2-char ISO country code (e.g., "us", "gb"). Defaults to "us".
        state: US state name with underscores (e.g., "california", "new_york").
               Only valid for US. Defaults to "california" for US.
        city: City name (e.g., "los_angeles", "san_francisco").
        postal_code: ZIP/postal code (e.g., "90210"). US only.

    Returns:
        dict with:
            - status: "SUCCESS" or "ERROR"
            - cdp_url: Chrome DevTools Protocol URL (on success)
            - machine_id: Container ID for later cleanup (on success)
            - validated_ip: IP address of the proxy (on success)
            - location: Validated location used (on success)
            - error: Error message (on failure)

    Example:
        >>> result = await configure_proxy(
        ...     country="us",
        ...     state="california",
        ...     city="los_angeles"
        ... )
        >>> if result["status"] == "SUCCESS":
        ...     print(f"CDP URL: {result['cdp_url']}")
        ...     print(f"Proxy IP: {result['validated_ip']}")
    """
    # Check if ChromeFleet is configured
    if not settings.CHROMEFLEET_URL:
        logger.error("CHROMEFLEET_URL not configured")
        return {
            "status": "ERROR",
            "error": "ChromeFleet service not configured. Set CHROMEFLEET_URL environment variable.",
        }

    if not settings.PROXY_URL_TEMPLATE:
        logger.error("PROXY_URL_TEMPLATE not configured")
        return {
            "status": "ERROR",
            "error": "Proxy URL template not configured. Set PROXY_URL_TEMPLATE environment variable.",
        }

    # Build location from parameters
    location = Location(
        country=country,
        state=state,
        city=city,
        postal_code=postal_code,
    )

    logger.info(
        "MCP configure_proxy called",
        location=location.model_dump(exclude_none=True),
    )

    # Generate a unique session ID for this request
    base_session_id = f"mcp_{uuid.uuid4().hex[:12]}"

    try:
        configurator = ProxyConfigurator(
            chromefleet_url=settings.CHROMEFLEET_URL,
            proxy_url_template=settings.PROXY_URL_TEMPLATE,
        )

        result = await configurator.configure_proxy(
            location=location,
            base_session_id=base_session_id,
        )

        logger.info(
            "MCP configure_proxy succeeded",
            cdp_url=result.cdp_url,
            machine_id=result.machine_id,
            validated_ip=str(result.validated_ip),
        )

        return {
            "status": "SUCCESS",
            "cdp_url": result.cdp_url,
            "machine_id": result.machine_id,
            "validated_ip": str(result.validated_ip),
            "location": result.location.model_dump(exclude_none=True),
        }

    except ProxyConfigurationError as e:
        logger.error(
            "MCP configure_proxy failed - all attempts exhausted",
            error=str(e),
            hierarchy_levels_tried=e.hierarchy_levels_tried,
            rotations_tried=e.rotations_tried,
            last_error=e.last_error,
        )
        return {
            "status": "ERROR",
            "error": str(e),
            "details": {
                "hierarchy_levels_tried": e.hierarchy_levels_tried,
                "rotations_tried": e.rotations_tried,
                "last_error": e.last_error,
            },
        }

    except Exception as e:
        logger.error(
            "MCP configure_proxy failed unexpectedly",
            error=str(e),
            error_type=type(e).__name__,
        )
        return {
            "status": "ERROR",
            "error": f"Unexpected error: {type(e).__name__}: {e}",
        }


@chromefleet_mcp.tool
async def stop_proxy_container_tool(machine_id: str) -> dict[str, Any]:
    """Stop a ChromeFleet proxy container.

    Use this tool to clean up containers that are no longer needed.
    Containers have a TTL and will be cleaned up automatically, but
    explicit cleanup is recommended when done.

    Args:
        machine_id: The machine_id returned from configure_proxy.

    Returns:
        dict with:
            - status: "SUCCESS" or "ERROR"
            - message: Status message
            - error: Error message (on failure)

    Example:
        >>> result = await stop_proxy_container(machine_id="mcp_abc123def456_0")
        >>> print(result["status"])  # "SUCCESS"
    """
    if not settings.CHROMEFLEET_URL:
        logger.error("CHROMEFLEET_URL not configured")
        return {
            "status": "ERROR",
            "error": "ChromeFleet service not configured.",
        }

    if not machine_id:
        return {
            "status": "ERROR",
            "error": "machine_id is required",
        }

    logger.info("MCP stop_proxy_container called", machine_id=machine_id)

    try:
        await stop_proxy_container(settings.CHROMEFLEET_URL, machine_id)

        logger.info("MCP stop_proxy_container succeeded", machine_id=machine_id)
        return {
            "status": "SUCCESS",
            "message": f"Container {machine_id} stopped successfully",
        }

    except Exception as e:
        logger.error(
            "MCP stop_proxy_container failed",
            machine_id=machine_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return {
            "status": "ERROR",
            "error": f"Failed to stop container: {e}",
        }
