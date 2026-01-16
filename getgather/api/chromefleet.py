"""REST API endpoints for ChromeFleet proxy configuration.

This module provides REST endpoints for configuring and managing ChromeFleet
proxy containers. The endpoints are mounted at /api/chromefleet.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from getgather.chromefleet import (
    Location,
    ProxyConfigurationError,
    ProxyConfigurator,
)
from getgather.chromefleet.proxy_configurator import stop_proxy_container
from getgather.config import settings

logger = logger.bind(topic="chromefleet_api")

# Create router with prefix
chromefleet_router = APIRouter(prefix="/chromefleet", tags=["chromefleet"])


class ConfigureProxyRequest(BaseModel):
    """Request model for proxy configuration."""

    country: str | None = Field(
        default=None,
        description="2-char ISO country code (e.g., 'us', 'gb'). Defaults to 'us'.",
    )
    state: str | None = Field(
        default=None,
        description="US state name with underscores (e.g., 'california'). US only.",
    )
    city: str | None = Field(
        default=None,
        description="City name (e.g., 'los_angeles').",
    )
    postal_code: str | None = Field(
        default=None,
        description="ZIP/postal code (e.g., '90210'). US only.",
    )


class ConfigureProxyResponse(BaseModel):
    """Response model for successful proxy configuration."""

    status: str = Field(description="Status: 'SUCCESS' or 'ERROR'")
    cdp_url: str | None = Field(
        default=None,
        description="Chrome DevTools Protocol URL for browser automation",
    )
    machine_id: str | None = Field(
        default=None,
        description="Container ID for later cleanup",
    )
    validated_ip: str | None = Field(
        default=None,
        description="External IP address of the proxy",
    )
    location: dict[str, Any] | None = Field(
        default=None,
        description="Validated location used for proxy configuration",
    )
    error: str | None = Field(
        default=None,
        description="Error message if status is 'ERROR'",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Additional error details if status is 'ERROR'",
    )


class StopContainerResponse(BaseModel):
    """Response model for container stop operation."""

    status: str = Field(description="Status: 'SUCCESS' or 'ERROR'")
    message: str | None = Field(
        default=None,
        description="Status message",
    )
    error: str | None = Field(
        default=None,
        description="Error message if status is 'ERROR'",
    )


@chromefleet_router.post("/configure-proxy", response_model=ConfigureProxyResponse)
async def configure_proxy_endpoint(request: ConfigureProxyRequest) -> ConfigureProxyResponse:
    """Configure a geo-targeted proxy through ChromeFleet.

    This endpoint starts a ChromeFleet container with a configured residential proxy
    targeting the specified location. The proxy is validated via both HTTP and
    CDP to ensure it's working correctly.

    Returns:
        ConfigureProxyResponse with cdp_url, machine_id, and validated_ip on success.

    Raises:
        HTTPException: 500 if ChromeFleet is not configured
        HTTPException: 503 if all proxy configuration attempts fail
    """
    # Check if ChromeFleet is configured
    if not settings.CHROMEFLEET_URL:
        logger.error("CHROMEFLEET_URL not configured")
        raise HTTPException(
            status_code=500,
            detail="ChromeFleet service not configured. Set CHROMEFLEET_URL environment variable.",
        )

    if not settings.PROXY_URL_TEMPLATE:
        logger.error("PROXY_URL_TEMPLATE not configured")
        raise HTTPException(
            status_code=500,
            detail="Proxy URL template not configured. Set PROXY_URL_TEMPLATE environment variable.",
        )

    # Build location from request
    location = Location(
        country=request.country,
        state=request.state,
        city=request.city,
        postal_code=request.postal_code,
    )

    logger.info(
        "REST configure_proxy called",
        location=location.model_dump(exclude_none=True),
    )

    # Generate a unique session ID for this request
    base_session_id = f"api_{uuid.uuid4().hex[:12]}"

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
            "REST configure_proxy succeeded",
            cdp_url=result.cdp_url,
            machine_id=result.machine_id,
            validated_ip=str(result.validated_ip),
        )

        return ConfigureProxyResponse(
            status="SUCCESS",
            cdp_url=result.cdp_url,
            machine_id=result.machine_id,
            validated_ip=str(result.validated_ip),
            location=result.location.model_dump(exclude_none=True),
        )

    except ProxyConfigurationError as e:
        logger.error(
            "REST configure_proxy failed - all attempts exhausted",
            error=str(e),
            hierarchy_levels_tried=e.hierarchy_levels_tried,
            rotations_tried=e.rotations_tried,
            last_error=e.last_error,
        )
        return ConfigureProxyResponse(
            status="ERROR",
            error=str(e),
            details={
                "hierarchy_levels_tried": e.hierarchy_levels_tried,
                "rotations_tried": e.rotations_tried,
                "last_error": e.last_error,
            },
        )

    except Exception as e:
        logger.error(
            "REST configure_proxy failed unexpectedly",
            error=str(e),
            error_type=type(e).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Proxy configuration failed: {type(e).__name__}: {e}",
        )


@chromefleet_router.post("/stop/{machine_id}", response_model=StopContainerResponse)
async def stop_container_endpoint(machine_id: str) -> StopContainerResponse:
    """Stop a ChromeFleet proxy container.

    Use this endpoint to clean up containers that are no longer needed.
    Containers have a TTL and will be cleaned up automatically, but
    explicit cleanup is recommended when done.

    Args:
        machine_id: The machine_id returned from configure_proxy.

    Returns:
        StopContainerResponse with status message.

    Raises:
        HTTPException: 500 if ChromeFleet is not configured
        HTTPException: 400 if machine_id is empty
    """
    if not settings.CHROMEFLEET_URL:
        logger.error("CHROMEFLEET_URL not configured")
        raise HTTPException(
            status_code=500,
            detail="ChromeFleet service not configured.",
        )

    if not machine_id or not machine_id.strip():
        raise HTTPException(
            status_code=400,
            detail="machine_id is required",
        )

    logger.info("REST stop_container called", machine_id=machine_id)

    try:
        await stop_proxy_container(settings.CHROMEFLEET_URL, machine_id)

        logger.info("REST stop_container succeeded", machine_id=machine_id)
        return StopContainerResponse(
            status="SUCCESS",
            message=f"Container {machine_id} stopped successfully",
        )

    except Exception as e:
        logger.error(
            "REST stop_container failed",
            machine_id=machine_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return StopContainerResponse(
            status="ERROR",
            error=f"Failed to stop container: {e}",
        )
