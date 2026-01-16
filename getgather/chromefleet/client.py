"""HTTP client for ChromeFleet API.

This module provides an async HTTP client for interacting with the ChromeFleet
service to manage browser containers and configure proxies.
"""

from typing import Any

import httpx
from loguru import logger

from getgather.chromefleet.exceptions import (
    ChromeFleetError,
    ChromeFleetUnavailableError,
    ContainerConfigError,
    ContainerStartError,
)
from getgather.chromefleet.models import ChromeFleetContainer

logger = logger.bind(topic="chromefleet_client")

# HTTP timeouts
DEFAULT_TIMEOUT = 30.0  # seconds
START_CONTAINER_TIMEOUT = 60.0  # Container start can take longer


class ChromeFleetClient:
    """Async HTTP client for ChromeFleet API.

    Usage:
        async with ChromeFleetClient(base_url="http://chromefleet:8300") as client:
            container = await client.start_container("session_123")
            await client.configure_proxy(container.machine_id, "http://proxy:7777")
            # ... use the container ...
            await client.stop_container(container.machine_id)
    """

    def __init__(self, base_url: str):
        """Initialize the ChromeFleet client.

        Args:
            base_url: Base URL of the ChromeFleet service (e.g., "http://chromefleet:8300")
        """
        self.base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ChromeFleetClient":
        """Enter async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=DEFAULT_TIMEOUT,
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure the HTTP client is initialized."""
        if self._client is None:
            raise RuntimeError(
                "ChromeFleetClient must be used as async context manager: "
                "async with ChromeFleetClient(...) as client:"
            )
        return self._client

    async def start_container(self, machine_id: str) -> ChromeFleetContainer:
        """Start a new ChromeFleet container.

        Args:
            machine_id: Unique identifier for the container (used as session ID)

        Returns:
            ChromeFleetContainer with machine_id, ip_address, and cdp_url

        Raises:
            ContainerStartError: If container start fails
            ChromeFleetUnavailableError: If ChromeFleet service is unavailable
        """
        client = self._ensure_client()

        try:
            logger.info("Starting ChromeFleet container", machine_id=machine_id)
            response = await client.get(
                f"/api/v1/start/{machine_id}",
                timeout=START_CONTAINER_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            container = ChromeFleetContainer(
                machine_id=machine_id,
                ip_address=data.get("ip_address", ""),
                cdp_url=data.get("cdp_url", ""),
            )

            logger.info(
                "ChromeFleet container started",
                machine_id=machine_id,
                ip_address=container.ip_address,
                cdp_url=container.cdp_url,
            )
            return container

        except httpx.ConnectError as e:
            logger.error(
                "ChromeFleet service unavailable",
                machine_id=machine_id,
                error=str(e),
            )
            raise ChromeFleetUnavailableError(f"ChromeFleet service unavailable: {e}") from e

        except httpx.HTTPStatusError as e:
            logger.error(
                "Container start failed",
                machine_id=machine_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise ContainerStartError(
                f"Container start failed with status {e.response.status_code}: {e}"
            ) from e

        except Exception as e:
            logger.error(
                "Unexpected error starting container",
                machine_id=machine_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ContainerStartError(f"Container start failed: {e}") from e

    async def configure_proxy(self, machine_id: str, proxy_url: str) -> None:
        """Configure proxy for a ChromeFleet container.

        This configures tinyproxy inside the container to use the specified
        upstream proxy URL.

        Args:
            machine_id: Container identifier
            proxy_url: Full proxy URL with credentials
                (e.g., "http://user:pass@proxy.oxylabs.io:7777")

        Raises:
            ContainerConfigError: If proxy configuration fails
            ChromeFleetUnavailableError: If ChromeFleet service is unavailable
        """
        client = self._ensure_client()

        # Mask credentials for logging
        masked_url = _mask_proxy_url(proxy_url)

        try:
            logger.info(
                "Configuring proxy for container",
                machine_id=machine_id,
                proxy_url=masked_url,
            )
            response = await client.post(
                f"/api/v1/configure/{machine_id}",
                json={"proxy_url": proxy_url},
            )
            response.raise_for_status()

            logger.info(
                "Proxy configured successfully",
                machine_id=machine_id,
            )

        except httpx.ConnectError as e:
            logger.error(
                "ChromeFleet service unavailable during proxy config",
                machine_id=machine_id,
                error=str(e),
            )
            raise ChromeFleetUnavailableError(f"ChromeFleet service unavailable: {e}") from e

        except httpx.HTTPStatusError as e:
            logger.error(
                "Proxy configuration failed",
                machine_id=machine_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise ContainerConfigError(
                f"Proxy configuration failed with status {e.response.status_code}: {e}"
            ) from e

        except Exception as e:
            logger.error(
                "Unexpected error configuring proxy",
                machine_id=machine_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ContainerConfigError(f"Proxy configuration failed: {e}") from e

    async def stop_container(self, machine_id: str) -> None:
        """Stop a ChromeFleet container.

        Args:
            machine_id: Container identifier

        Raises:
            ChromeFleetError: If container stop fails
        """
        client = self._ensure_client()

        try:
            logger.info("Stopping ChromeFleet container", machine_id=machine_id)
            response = await client.get(f"/api/v1/stop/{machine_id}")
            response.raise_for_status()

            logger.info("ChromeFleet container stopped", machine_id=machine_id)

        except httpx.ConnectError as e:
            logger.warning(
                "ChromeFleet service unavailable during stop (container may already be stopped)",
                machine_id=machine_id,
                error=str(e),
            )
            # Don't raise - container might already be stopped

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    "Container not found during stop (may already be stopped)",
                    machine_id=machine_id,
                )
            else:
                logger.error(
                    "Container stop failed",
                    machine_id=machine_id,
                    status_code=e.response.status_code,
                    error=str(e),
                )
                raise ChromeFleetError(
                    f"Container stop failed with status {e.response.status_code}: {e}"
                ) from e

        except Exception as e:
            logger.error(
                "Unexpected error stopping container",
                machine_id=machine_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ChromeFleetError(f"Container stop failed: {e}") from e

    async def query_container(self, machine_id: str) -> dict[str, Any]:
        """Query the status of a ChromeFleet container.

        Args:
            machine_id: Container identifier

        Returns:
            Dict containing container status information

        Raises:
            ChromeFleetError: If query fails
        """
        client = self._ensure_client()

        try:
            logger.debug("Querying ChromeFleet container", machine_id=machine_id)
            response = await client.get(f"/api/v1/query/{machine_id}")
            response.raise_for_status()

            data = response.json()
            logger.debug(
                "Container query successful",
                machine_id=machine_id,
                status=data,
            )
            return data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("Container not found", machine_id=machine_id)
                return {"status": "not_found"}
            raise ChromeFleetError(
                f"Container query failed with status {e.response.status_code}: {e}"
            ) from e

        except Exception as e:
            logger.error(
                "Unexpected error querying container",
                machine_id=machine_id,
                error=str(e),
            )
            raise ChromeFleetError(f"Container query failed: {e}") from e


def _mask_proxy_url(url: str) -> str:
    """Mask credentials in proxy URL for safe logging.

    Args:
        url: Proxy URL potentially containing credentials

    Returns:
        URL with password masked as ****
    """
    from urllib.parse import urlparse

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
