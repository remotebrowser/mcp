from functools import cached_property

from loguru import logger
from pydantic import BaseModel


class AuthSettings(BaseModel):
    OAUTH_ORIGIN: str = ""

    FIRST_PARTY_OAUTH_PROVIDER_NAME: str = ""
    FIRST_PARTY_APPS: dict[str, str] = dict()  # app key -> app name

    OAUTH_GOOGLE_CLIENT_ID: str = ""
    OAUTH_GOOGLE_CLIENT_SECRET: str = ""

    OAUTH_JWT_SIGNING_KEY: str = ""
    OAUTH_REDIS_URL: str = ""

    @cached_property
    def auth_enabled(self) -> bool:
        if not self.OAUTH_ORIGIN:
            logger.warning("Auth is disabled because OAUTH_ORIGIN is not provided")
            return False

        providers: list[str] = []
        if self.FIRST_PARTY_OAUTH_PROVIDER_NAME and self.FIRST_PARTY_APPS:
            providers.append(self.FIRST_PARTY_OAUTH_PROVIDER_NAME)
        if self.OAUTH_GOOGLE_CLIENT_ID and self.OAUTH_GOOGLE_CLIENT_SECRET:
            providers.append("google")

        if not providers:
            logger.warning("Auth is disabled because no OAuth providers are configured")
            return False

        logger.info(f"Auth is enabled with providers: {', '.join(providers)}")
        return True
