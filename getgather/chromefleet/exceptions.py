"""Exception types for ChromeFleet proxy configuration.

This module defines the exception hierarchy for ChromeFleet operations:
- ChromeFleetError: Base exception for all ChromeFleet errors
- ChromeFleetUnavailableError: Service unavailable
- ContainerStartError: Container start failure
- ContainerConfigError: Configuration failure
- ProxyConfigurationError: All proxy configuration attempts exhausted
"""


class ChromeFleetError(Exception):
    """Base exception for ChromeFleet operations.

    All ChromeFleet-specific exceptions inherit from this class,
    allowing callers to catch all ChromeFleet errors with a single except clause.
    """

    pass


class ChromeFleetUnavailableError(ChromeFleetError):
    """Raised when the ChromeFleet service is unavailable.

    This typically occurs when:
    - The ChromeFleet service is down
    - Network connectivity issues prevent reaching the service
    - The service URL is misconfigured
    """

    pass


class ContainerStartError(ChromeFleetError):
    """Raised when a ChromeFleet container fails to start.

    This can occur due to:
    - Resource exhaustion (no available containers)
    - Invalid machine ID
    - Internal ChromeFleet errors
    """

    pass


class ContainerConfigError(ChromeFleetError):
    """Raised when container configuration fails.

    This typically occurs when:
    - Proxy URL format is invalid
    - Tinyproxy configuration fails
    - Container is not in a configurable state
    """

    pass


class ProxyConfigurationError(ChromeFleetError):
    """Raised when all proxy configuration attempts are exhausted.

    This occurs after trying:
    - All rotations (0, 1, 2) for each hierarchy level
    - All hierarchy levels (postal_code -> city -> state -> country)

    The error message includes details about what was attempted.
    """

    def __init__(
        self,
        message: str,
        hierarchy_levels_tried: int = 0,
        rotations_tried: int = 0,
        last_error: str | None = None,
    ):
        """Initialize ProxyConfigurationError.

        Args:
            message: Error description
            hierarchy_levels_tried: Number of location hierarchy levels attempted
            rotations_tried: Total number of rotations attempted
            last_error: Last error message encountered during attempts
        """
        super().__init__(message)
        self.hierarchy_levels_tried = hierarchy_levels_tried
        self.rotations_tried = rotations_tried
        self.last_error = last_error
