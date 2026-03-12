import os
from functools import lru_cache
from typing import Any

import yaml
from loguru import logger

from getgather.browser.proxy_types import ProxyConfig
from getgather.config import settings


@lru_cache(maxsize=1)
def load_proxy_configs() -> dict[str, ProxyConfig]:
    """Load proxy configurations from environment variable or YAML file.

    Priority:
    1. PROXIES_CONFIG environment variable
    2. proxies.yaml file in project root (local development)
    3. Empty dict (no proxies configured)

    Returns:
        dict: Mapping of proxy identifiers (e.g., 'proxy-0') to ProxyConfig objects

    Raises:
        yaml.YAMLError: If YAML is malformed
        ValueError: If configuration structure is invalid
    """
    # Option 1: Load from environment variable
    yaml_content = os.getenv("PROXIES_CONFIG")

    if yaml_content:
        logger.info("Loading proxy configurations from PROXIES_CONFIG environment variable")
        try:
            data = yaml.safe_load(yaml_content)
            return _parse_proxy_configs(data)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse PROXIES_CONFIG YAML: {e}")
            raise

    # Option 2: Load from local file (development)
    yaml_path = settings.data_dir / "proxies.yaml"

    if yaml_path.exists():
        logger.info(f"Loading proxy configurations from {yaml_path}")
        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            return _parse_proxy_configs(data)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse {yaml_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to read {yaml_path}: {e}")
            raise

    # Option 3: No proxies configured
    logger.info(
        "No proxy configuration found (no PROXIES_CONFIG env var or proxies.yaml file). "
        "Proxies are disabled."
    )
    return {}


def _parse_proxy_configs(data: dict[str, Any] | None) -> dict[str, ProxyConfig]:
    """Parse YAML data into ProxyConfig objects.

    Expected YAML structure:
        proxies:
          proxy-0:
            type: none
          proxy-1:
            type: proxy_1_service
            url: http://localhost:8889
            username_template: "user-{session_id}-country-{country}"
            password: "secret"
          proxy-2:
            type: proxy_2_service
            url_template: "http://customer-{session_id}:pass@proxy.com:7777"

    Args:
        data: Parsed YAML dictionary

    Returns:
        dict: Mapping of proxy identifiers to ProxyConfig objects

    Raises:
        ValueError: If configuration structure is invalid
    """

    if not data or "proxies" not in data:
        logger.warning(
            "Invalid proxy configuration: missing 'proxies' key. Expected structure: "
            "proxies:\n  proxy-0:\n    type: none"
        )
        return {}

    proxies_data: Any = data["proxies"]
    if not isinstance(proxies_data, dict):
        raise ValueError(
            f"Invalid proxy configuration: 'proxies' must be a dict, got {type(proxies_data)}"
        )

    configs: dict[str, ProxyConfig] = {}

    # YAML parsing unavoidably returns Any types - we validate at runtime with isinstance()
    for proxy_key, proxy_data in proxies_data.items():  # type: ignore[attr-defined]
        # Validate types from YAML
        if not isinstance(proxy_key, str):
            logger.warning(f"Skipping proxy with non-string key: {type(proxy_key)}")  # type: ignore[arg-type]
            continue
        if not isinstance(proxy_data, dict):
            logger.warning(f"Skipping {proxy_key}: invalid data type {type(proxy_data)}")  # type: ignore[arg-type]
            continue

        # Check if proxy is disabled
        if not proxy_data.get("enabled", True):  # type: ignore[union-attr]
            logger.info(f"Skipping {proxy_key}: disabled in configuration")
            continue

        try:
            # Extract configuration fields from YAML
            proxy_type_raw = proxy_data.get("type", "unknown")  # type: ignore[union-attr]
            url_raw = proxy_data.get("url")  # type: ignore[union-attr]
            url_template_raw = proxy_data.get("url_template")  # type: ignore[union-attr]
            username_template_raw = proxy_data.get("username_template")  # type: ignore[union-attr]
            password_raw = proxy_data.get("password")  # type: ignore[union-attr]

            # Convert to proper types
            proxy_type: str = str(proxy_type_raw) if proxy_type_raw else "unknown"  # type: ignore[arg-type]
            url: str | None = str(url_raw) if url_raw is not None else None  # type: ignore[arg-type]
            url_template: str | None = (
                str(url_template_raw) if url_template_raw is not None else None  # type: ignore[arg-type]
            )
            username_template: str | None = (
                str(username_template_raw) if username_template_raw is not None else None  # type: ignore[arg-type]
            )
            password: str | None = str(password_raw) if password_raw is not None else None  # type: ignore[arg-type]

            # Validate: must have either url_template OR url (unless type is 'none')
            if proxy_type != "none" and not url_template and not url:
                logger.warning(
                    f"Skipping {proxy_key}: missing both 'url' and 'url_template'. "
                    f"At least one is required (unless type is 'none')."
                )
                continue

            # Create ProxyConfig instance
            config = ProxyConfig(
                proxy_type=proxy_type,
                url=url,
                url_template=url_template,
                username_template=username_template,
                password=password,
            )

            configs[proxy_key] = config
            logger.info(f"Loaded proxy configuration for {proxy_key}: type={proxy_type}")

        except Exception as e:
            logger.error(f"Failed to parse configuration for {proxy_key}: {e}")
            continue

    logger.info(f"Successfully loaded {len(configs)} proxy configuration(s)")
    return configs
