"""Main orchestrator for proxy configuration with ChromeFleet.

This module implements the core logic for:
- Building and caching proxy configurations
- Managing location hierarchy fallback
- Session rotation for proxy IP changes
- Coordinating ChromeFleet containers and validation
"""

import asyncio
import hashlib
import re
from typing import Any

from cachetools import TTLCache
from loguru import logger

from getgather.chromefleet.client import ChromeFleetClient
from getgather.chromefleet.exceptions import (
    ChromeFleetError,
    ProxyConfigurationError,
)
from getgather.chromefleet.location_hierarchy import (
    DEFAULT_HIERARCHY_LEVELS,
    build_location_hierarchy,
)
from getgather.chromefleet.models import (
    ConfiguredProxy,
    HierarchyLevel,
    Location,
)
from getgather.chromefleet.validation import (
    mask_credentials,
    validate_proxy_cdp,
    validate_proxy_http,
)

logger = logger.bind(topic="chromefleet_configurator")

# Cache configuration
CACHE_TTL_SECONDS = 60 * 20  # 20 minutes
CACHE_MAX_SIZE = 1000

# Module-level singleton cache and lock
_validation_cache: TTLCache[str, ConfiguredProxy] = TTLCache(
    maxsize=CACHE_MAX_SIZE, ttl=CACHE_TTL_SECONDS
)
_cache_lock = asyncio.Lock()

# Number of rotations to try per hierarchy level
MAX_ROTATIONS = 3  # 0, 1, 2


def _get_location_hash(location: Location | None) -> str:
    """Generate a stable hash for a location.

    This hash is used for:
    1. Cache key generation
    2. Session ID generation (to rotate proxy IP on location change)

    Uses SHA-256 with 16 chars to minimize collision risk.
    """
    if not location:
        return "no_location"

    parts = [
        location.country or "",
        location.state or "",
        location.city or "",
        location.postal_code or "",
    ]
    location_str = "_".join(parts)
    return hashlib.sha256(location_str.encode()).hexdigest()[:16]


def _get_cache_key(base_session_id: str, location: Location | None) -> str:
    """Generate cache key for validation results."""
    location_hash = _get_location_hash(location)
    return f"{base_session_id}:{location_hash}"


def _get_session_id_with_location(
    base_session_id: str, location: Location | None, rotation: int
) -> str:
    """Generate session ID that includes location hash and rotation.

    This ensures proxy providers give a new IP when:
    - Location changes (different hash)
    - Rotation changes (different suffix)

    Format: {base_session_id}_{location_hash}_{rotation}
    """
    location_hash = _get_location_hash(location)
    return f"{base_session_id}_{location_hash}_{rotation}"


class ProxyConfigurator:
    """Orchestrator for proxy configuration with ChromeFleet.

    This class coordinates:
    - ChromeFleet container management
    - Proxy URL building from templates
    - Location hierarchy fallback
    - Session rotation
    - Validation (HTTP and CDP)
    - Result caching

    Usage:
        configurator = ProxyConfigurator(
            chromefleet_url="http://chromefleet:8300",
            proxy_url_template="http://user-{session_id}-cc-{country}:pass@proxy.com:7777"
        )
        result = await configurator.configure_proxy(
            location=Location(country="us", state="california"),
            base_session_id="my_session"
        )
        # result.cdp_url is ready to use
    """

    def __init__(
        self,
        chromefleet_url: str,
        proxy_url_template: str,
        hierarchy_levels: list[HierarchyLevel] | None = None,
    ):
        """Initialize the ProxyConfigurator.

        Args:
            chromefleet_url: Base URL of the ChromeFleet service
            proxy_url_template: URL template with placeholders:
                - {session_id}: Unique session ID
                - {country}: 2-char ISO country code
                - {state}: State name (US only)
                - {city}: City name
                - {city_compacted}: City without spaces
                - {postal_code}: ZIP/postal code
            hierarchy_levels: Custom hierarchy levels for fallback (optional)
        """
        self.chromefleet_url = chromefleet_url
        self.proxy_url_template = proxy_url_template
        self.hierarchy_levels = hierarchy_levels or DEFAULT_HIERARCHY_LEVELS

    async def configure_proxy(
        self,
        location: Location,
        base_session_id: str,
    ) -> ConfiguredProxy:
        """Configure a proxy for the given location.

        This is the main entry point. It:
        1. Checks the cache for an existing configuration
        2. Builds a location hierarchy for fallback
        3. Tries each hierarchy level with multiple rotations
        4. Validates the proxy (HTTP + CDP)
        5. Caches and returns the result

        Args:
            location: Target location for the proxy
            base_session_id: Base session ID (will be combined with location hash)

        Returns:
            ConfiguredProxy with cdp_url, machine_id, validated_ip, and location

        Raises:
            ProxyConfigurationError: If all attempts are exhausted
            ChromeFleetError: If ChromeFleet service errors occur
        """
        # Check cache first
        cache_key = _get_cache_key(base_session_id, location)
        async with _cache_lock:
            cached_result = _validation_cache.get(cache_key)
        if cached_result is not None:
            logger.info(
                "Using cached proxy configuration",
                cache_key=cache_key,
                cdp_url=cached_result.cdp_url,
                machine_id=cached_result.machine_id,
            )
            return cached_result

        # Build location hierarchy
        hierarchy = build_location_hierarchy(location, self.hierarchy_levels)
        if not hierarchy:
            raise ProxyConfigurationError(
                f"Failed to build location hierarchy for {location.model_dump(exclude_none=True)}"
            )

        logger.info(
            f"Starting proxy configuration with {len(hierarchy)} hierarchy levels",
            location=location.model_dump(exclude_none=True),
            hierarchy_levels=[loc.model_dump(exclude_none=True) for loc in hierarchy],
        )

        total_rotations_tried = 0
        last_error: str | None = None

        # Try each hierarchy level
        for level_idx, hierarchy_location in enumerate(hierarchy, start=1):
            logger.info(
                f"Trying hierarchy level {level_idx}/{len(hierarchy)}",
                location=hierarchy_location.model_dump(exclude_none=True),
            )

            result = await self._try_location_with_rotations(hierarchy_location, base_session_id)
            if result is not None:
                # Cache the successful result
                async with _cache_lock:
                    _validation_cache[cache_key] = result
                logger.info(
                    "Proxy configuration succeeded",
                    level=level_idx,
                    cdp_url=result.cdp_url,
                    machine_id=result.machine_id,
                    validated_ip=str(result.validated_ip),
                )
                return result

            total_rotations_tried += MAX_ROTATIONS
            last_error = f"All rotations failed at level {level_idx}"

        # All levels exhausted
        raise ProxyConfigurationError(
            f"All proxy configuration attempts exhausted for location "
            f"{location.model_dump(exclude_none=True)}",
            hierarchy_levels_tried=len(hierarchy),
            rotations_tried=total_rotations_tried,
            last_error=last_error,
        )

    async def _try_location_with_rotations(
        self,
        location: Location,
        base_session_id: str,
    ) -> ConfiguredProxy | None:
        """Try to configure proxy for a location with multiple rotations.

        Args:
            location: Location to try
            base_session_id: Base session ID

        Returns:
            ConfiguredProxy if successful, None if all rotations failed
        """
        for rotation in range(MAX_ROTATIONS):
            session_id = _get_session_id_with_location(base_session_id, location, rotation)
            logger.debug(
                f"Trying rotation {rotation}/{MAX_ROTATIONS - 1}",
                session_id=session_id,
                location=location.model_dump(exclude_none=True),
            )

            result = await self._try_single_configuration(location, session_id)
            if result is not None:
                return result

        return None

    async def _try_single_configuration(
        self,
        location: Location,
        session_id: str,
    ) -> ConfiguredProxy | None:
        """Try a single proxy configuration attempt.

        Args:
            location: Target location
            session_id: Full session ID (includes location hash and rotation)

        Returns:
            ConfiguredProxy if successful, None if failed
        """
        machine_id = session_id
        container = None

        try:
            async with ChromeFleetClient(self.chromefleet_url) as client:
                # Step 1: Start container
                logger.debug("Starting ChromeFleet container", machine_id=machine_id)
                container = await client.start_container(machine_id)

                # Step 2: Build proxy URL
                proxy_url = self._build_proxy_url(location, session_id)
                logger.debug(
                    "Built proxy URL",
                    proxy_url=mask_credentials(proxy_url),
                )

                # Step 3: Configure proxy in container
                await client.configure_proxy(machine_id, proxy_url)

                # Step 4: HTTP validation
                logger.debug("Running HTTP validation")
                http_result = await validate_proxy_http(proxy_url)
                if not http_result.success:
                    logger.warning(
                        "HTTP validation failed",
                        error=http_result.error,
                        is_location_error=http_result.is_location_error,
                    )
                    await self._cleanup_failed_container(client, machine_id)
                    # If it's not a location error, we might want to fail fast
                    # but for now, continue to next rotation
                    return None

                # Step 5: CDP validation
                logger.debug("Running CDP validation", cdp_url=container.cdp_url)
                cdp_result = await validate_proxy_cdp(container.cdp_url)
                if not cdp_result.success:
                    logger.warning(
                        "CDP validation failed",
                        error=cdp_result.error,
                        is_location_error=cdp_result.is_location_error,
                    )
                    await self._cleanup_failed_container(client, machine_id)
                    return None

                # Success! Return configured proxy
                # Use CDP validated IP as it's the more reliable validation
                return ConfiguredProxy(
                    cdp_url=container.cdp_url,
                    machine_id=machine_id,
                    validated_ip=cdp_result.ip_address,  # type: ignore[arg-type]
                    location=location,
                )

        except ChromeFleetError as e:
            logger.warning(
                "ChromeFleet error during configuration",
                machine_id=machine_id,
                error=str(e),
            )
            if container:
                async with ChromeFleetClient(self.chromefleet_url) as client:
                    await self._cleanup_failed_container(client, machine_id)
            return None

        except Exception as e:
            logger.error(
                "Unexpected error during proxy configuration",
                machine_id=machine_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            if container:
                async with ChromeFleetClient(self.chromefleet_url) as client:
                    await self._cleanup_failed_container(client, machine_id)
            return None

    def _build_proxy_url(self, location: Location, session_id: str) -> str:
        """Build proxy URL from template with location and session values.

        Args:
            location: Location with geo-targeting values
            session_id: Session ID for the proxy

        Returns:
            Fully constructed proxy URL
        """
        # Build values dict from session_id and location
        values: dict[str, Any] = {"session_id": session_id}
        values.update(location.to_template_values())

        # Split by placeholders and rebuild
        parts: list[str] = []
        current = self.proxy_url_template
        placeholders: list[str] = re.findall(r"\{([^}]+)\}", self.proxy_url_template)

        for placeholder in placeholders:
            before, _, after = current.partition(f"{{{placeholder}}}")

            if placeholder in values and values[placeholder] is not None:
                parts.append(before + str(values[placeholder]))

            current = after

        # Add any remaining text
        if current:
            parts.append(current)

        result = "".join(parts)
        # Clean up separators at start/end
        result = result.strip("-_")

        return result

    async def _cleanup_failed_container(self, client: ChromeFleetClient, machine_id: str) -> None:
        """Stop a container that failed validation.

        Args:
            client: ChromeFleet client
            machine_id: Container to stop
        """
        try:
            logger.debug("Cleaning up failed container", machine_id=machine_id)
            await client.stop_container(machine_id)
        except Exception as e:
            # Log but don't raise - cleanup failures shouldn't block retry logic
            logger.warning(
                "Failed to cleanup container",
                machine_id=machine_id,
                error=str(e),
            )


async def stop_proxy_container(chromefleet_url: str, machine_id: str) -> None:
    """Stop a ChromeFleet container.

    Convenience function for stopping containers without full configurator setup.

    Args:
        chromefleet_url: ChromeFleet service URL
        machine_id: Container to stop
    """
    async with ChromeFleetClient(chromefleet_url) as client:
        await client.stop_container(machine_id)
