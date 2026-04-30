from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from getgather.auth.settings import AuthSettings

FRIENDLY_CHARS = "23456789abcdefghijkmnpqrstuvwxyz"

PROJECT_DIR = Path(__file__).resolve().parent.parent


class Settings(AuthSettings, BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env", env_ignore_empty=True, extra="ignore"
    )
    ENVIRONMENT: str = "local"
    GIT_REV: str = ""

    DATA_DIR: str = ""

    CHROMEFLEET_URL: str = ""

    @property
    def effective_chromefleet_url(self) -> str:
        """Returns CHROMEFLEET_URL if set, otherwise falls back to the local backend."""
        return self.CHROMEFLEET_URL or "http://127.0.0.1:23456"

    # Browser fleet (ChromeFleet integrated)
    CONTAINER_IMAGE: str = "ghcr.io/remotebrowser/chromium-live"
    CONTAINER_HOST: str = ""

    # Residential proxy (Massive)
    MASSIVE_PROXY_USERNAME: str = ""
    MASSIVE_PROXY_PASSWORD: str = ""

    # MaxMind GeoIP
    MAXMIND_ACCOUNT_ID: int = 0
    MAXMIND_LICENSE_KEY: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""
    LOGFIRE_TOKEN: str = ""

    @property
    def MASSIVE_PROXY_ENABLED(self) -> bool:
        return bool(self.MASSIVE_PROXY_USERNAME and self.MASSIVE_PROXY_PASSWORD)

    @property
    def MAXMIND_ENABLED(self) -> bool:
        return bool(self.MAXMIND_ACCOUNT_ID and self.MAXMIND_LICENSE_KEY)

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


settings = Settings()
