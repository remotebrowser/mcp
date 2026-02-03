"""Proxy configuration types.

This module contains the core proxy configuration data structure, separated
from business logic to avoid circular dependencies.
"""

import re
from urllib.parse import urlparse

from loguru import logger


class ProxyConfig:
    """Represents a configured proxy from YAML configuration.

    This is a pure data class that handles URL parsing and stores proxy
    configuration data. Business logic (template building) is in proxy_builder.py.
    """

    def __init__(
        self,
        proxy_type: str = "unknown",
        url: str | None = None,
        url_template: str | None = None,
        username_template: str | None = None,
        password: str | None = None,
    ):
        """Initialize proxy configuration from YAML data.

        Supports two configuration formats:
        1. Separate components: url + username_template + password
        2. Full URL template: url_template (includes credentials and dynamic params)

        Args:
            proxy_type: Type identifier (e.g., 'proxy-1', 'proxy-2', 'none')
            url: Proxy server URL (e.g., 'http://proxy.example.com:8888')
            url_template: Full URL with credentials and dynamic params (e.g., 'http://{username}:{password}@proxy.com:7777')
            username_template: Username with dynamic params (e.g., 'user-{session_id}-country-{country}')
            password: Proxy password
        """
        self.proxy_type = proxy_type
        self.url_template = url_template
        self.username_template = username_template

        # Parse URL to extract username, password, and server
        self.base_username: str | None = None
        self.password: str | None = password
        self.server: str | None = None
        self.masked_url: str | None = None  # URL with credentials masked for logging

        # If url_template is provided, we'll handle it differently in build()
        # Otherwise, parse the url for separate components
        if url and not url_template:
            self._parse_url(url)

    def _parse_url(self, url: str) -> None:
        """Parse URL to extract base username, password, and server.

        Args:
            url: Full URL with credentials (e.g., 'user:pass@host:port' or 'http://user:pass@host:port')
        """
        # Add scheme if not present to help urlparse
        url_to_parse = url
        if "://" not in url:
            url_to_parse = f"http://{url}"

        # Create masked version for logging (mask credentials once)
        self.masked_url = re.sub(r"://[^@]+@", "://***@", url_to_parse)

        parsed = urlparse(url_to_parse)

        # Extract username and password from URL
        if parsed.username:
            self.base_username = parsed.username
        if parsed.password:
            self.password = parsed.password

        # Reconstruct server URL without credentials
        if parsed.hostname:
            scheme = parsed.scheme or "http"
            port = f":{parsed.port}" if parsed.port else ""
            self.server = f"{scheme}://{parsed.hostname}{port}"
        else:
            logger.warning(f"Could not parse hostname from URL: {self.masked_url}")
            self.server = url
