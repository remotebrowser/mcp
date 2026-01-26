from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from getgather.auth.settings import AuthSettings
from getgather.browser.proxy_types import ProxyConfig

PROJECT_DIR = Path(__file__).resolve().parent.parent


class Settings(AuthSettings, BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env", env_ignore_empty=True, extra="ignore"
    )
    ENVIRONMENT: str = "local"
    GIT_REV: str = ""

    DATA_DIR: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""
    LOGFIRE_TOKEN: str = ""

    # Default Proxy Type (optional - e.g., "proxy-0", "proxy-1")
    # If not set, no proxy will be used unless specified via x-proxy-type header
    DEFAULT_PROXY_TYPE: str = ""

    # Max session age, in minutes
    BROWSER_SESSION_AGE: int = 60

    @property
    def data_dir(self) -> Path:
        path = Path(self.DATA_DIR).resolve() if self.DATA_DIR else PROJECT_DIR / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def screenshots_dir(self) -> Path:
        path = self.data_dir / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def profiles_dir(self) -> Path:
        path = self.data_dir / "profiles"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def proxy_configs(self) -> dict[str, ProxyConfig]:
        """Load proxy configurations from YAML file or environment variable (cached).

        Returns:
            dict: Mapping of proxy identifiers (e.g., 'proxy-0') to ProxyConfig objects
        """
        from getgather.browser.proxy_loader import load_proxy_configs

        return load_proxy_configs()


settings = Settings()
