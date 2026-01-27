import re
from typing import Any

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider, GoogleTokenVerifier
from key_value.aio.stores.redis import RedisStore
from loguru import logger
from mcp.server.auth.provider import AccessToken as MCPAccessToken

from getgather.config import settings

FIRST_PARTY_USER_ID_PATTERN = re.compile("^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
GOOGLE_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def verify_first_party_oauth_token(token: str) -> AccessToken | None:
    """
    Valid first party OAuth token format X_Y_Z, where
    - X is settings.FIRST_PARTY_OAUTH_PROVIDER_NAME
    - Y is an app key, i.e., one of settings.FIRST_PARTY_APPS.keys()
    - Z is a string matching FIRST_PARTY_USER_ID_PATTERN
    """
    parts = token.split("_")
    provider_name = parts[0]
    if (
        len(parts) < 3
        or provider_name != settings.FIRST_PARTY_OAUTH_PROVIDER_NAME
        or parts[1] not in settings.FIRST_PARTY_APPS
    ):
        logger.warning("Invalid first party OAuth token", token=token)
        return None

    sub = "_".join(parts[2:])
    if not FIRST_PARTY_USER_ID_PATTERN.match(sub):
        logger.warning(
            "Getgather user id does not match pattern",
            user_id=sub,
            pattern=FIRST_PARTY_USER_ID_PATTERN.pattern,
        )
        return None

    app_name = settings.FIRST_PARTY_APPS[parts[1]]

    return AccessToken(
        token=token,
        client_id=parts[1],
        scopes=GOOGLE_OAUTH_SCOPES,  # the same scopes as GoogleProvider requires
        claims={"sub": sub, "app_name": app_name, "auth_provider": provider_name},
    )


class CustomTokenVerifier(GoogleTokenVerifier):
    """Custom TokenVerifier to verify first party OAuth tokens before delegating to GoogleTokenVerifier."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if settings.FIRST_PARTY_OAUTH_PROVIDER_NAME and token.startswith(
            settings.FIRST_PARTY_OAUTH_PROVIDER_NAME
        ):
            return verify_first_party_oauth_token(token)
        else:
            access_token = await super().verify_token(token)
            if not access_token:
                logger.debug("Failed to verify Google token")
                return None
            access_token.claims["auth_provider"] = "google"
            return access_token


class CustomOAuthProvider(GoogleProvider):
    """Custom OAuthProvider to allow first party OAuth tokens in addition to Google OAuth tokens."""

    def __init__(self, *args: Any, **kwargs: Any):
        extra_args: dict[str, Any] = {}
        if settings.OAUTH_JWT_SIGNING_KEY:
            extra_args["jwt_signing_key"] = settings.OAUTH_JWT_SIGNING_KEY
        if settings.OAUTH_REDIS_URL:
            extra_args["client_storage"] = RedisStore(url=settings.OAUTH_REDIS_URL)

        super().__init__(
            client_id=settings.OAUTH_GOOGLE_CLIENT_ID,
            client_secret=settings.OAUTH_GOOGLE_CLIENT_SECRET,
            base_url=settings.OAUTH_ORIGIN,
            required_scopes=GOOGLE_OAUTH_SCOPES,
            **extra_args,
        )
        self._token_validator = CustomTokenVerifier(required_scopes=GOOGLE_OAUTH_SCOPES)

    async def load_access_token(self, token: str) -> MCPAccessToken | None:
        if settings.FIRST_PARTY_OAUTH_PROVIDER_NAME and token.startswith(
            settings.FIRST_PARTY_OAUTH_PROVIDER_NAME
        ):
            return verify_first_party_oauth_token(token)
        else:
            return await super().load_access_token(token)
