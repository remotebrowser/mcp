"""ChromeFleet proxy configuration package.

This package provides functionality to configure and validate proxies
through ChromeFleet containers with intelligent location-based fallback.

Main components:
- models: Pydantic models for Location, ConfiguredProxy, etc.
- client: HTTP client for ChromeFleet API
- location_hierarchy: Builds fallback location hierarchy
- validation: HTTP and CDP proxy validation
- proxy_configurator: Main orchestrator with caching
- exceptions: Exception types for error handling
"""

from getgather.chromefleet.exceptions import (
    ChromeFleetError,
    ChromeFleetUnavailableError,
    ContainerConfigError,
    ContainerStartError,
    ProxyConfigurationError,
)
from getgather.chromefleet.models import (
    ChromeFleetContainer,
    ConfiguredProxy,
    HierarchyLevel,
    Location,
    ProxyValidationResult,
)
from getgather.chromefleet.proxy_configurator import ProxyConfigurator

__all__ = [
    # Exceptions
    "ChromeFleetError",
    "ChromeFleetUnavailableError",
    "ContainerConfigError",
    "ContainerStartError",
    "ProxyConfigurationError",
    # Models
    "ChromeFleetContainer",
    "ConfiguredProxy",
    "HierarchyLevel",
    "Location",
    "ProxyValidationResult",
    # Main class
    "ProxyConfigurator",
]
