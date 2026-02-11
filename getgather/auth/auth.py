import re
import socket
from typing import cast

from fastapi import FastAPI
from fastmcp.server.dependencies import get_access_token
from loguru import logger
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import TokenVerifier
from pydantic import BaseModel, field_validator, model_validator
from starlette.datastructures import Headers
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.responses import RedirectResponse
from starlette.types import Receive, Scope, Send

from getgather.auth.provider import CustomOAuthProvider
from getgather.config import settings


class RequireAuthMiddlewareCustom(RequireAuthMiddleware):
    """
    Custom RequireAuthMiddleware to require authentication for MCP routes.
    If requests are from non mcp clients, redirect to the home page.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get("path")

        if path and path.startswith("/mcp"):
            headers = Headers(scope=scope)
            accept = headers.get("accept") or ""

            if "text/event-stream" not in accept:
                # if client does not accept text/event-stream, redirect to the home page
                response = RedirectResponse(url="/", status_code=307)
                await response(scope, receive, send)
            else:
                await super().__call__(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def setup_mcp_auth(app: FastAPI, mcp_routes: list[str]):
    if not settings.auth_enabled:
        logger.info("MCP authentication is disabled")
        return

    logger.info("Setting up MCP authentication")

    auth_provider = CustomOAuthProvider()

    # Set up OAuth routes
    for route in auth_provider.get_routes():
        app.add_route(
            route.path,
            route.endpoint,
            list(route.methods) if route.methods else [],
        )

        # handle '/.well-known/oauth-authorization-server/mcp-*' and
        # '/.well-known/oauth-authorization-server/mcp-*'
        if route.path.startswith("/.well-known"):
            for mcp_route in mcp_routes:
                app.add_route(
                    f"{route.path}{mcp_route}",
                    route.endpoint,
                    list(route.methods) if route.methods else [],
                )

    # Set up OAuth middlewares, in this order:
    auth_middleware = [
        Middleware(
            RequireAuthMiddlewareCustom,  # verify auth for MCP routes
            auth_provider.required_scopes,
        ),
        Middleware(AuthContextMiddleware),  # store the auth user in the context_var
        Middleware(
            AuthenticationMiddleware,  # manage oauth flow
            backend=BearerAuthBackend(cast(TokenVerifier, auth_provider)),
        ),
    ]

    for middleware in auth_middleware:
        app.add_middleware(middleware.cls, *middleware.args, **middleware.kwargs)


class AuthUser(BaseModel):
    sub: str
    auth_provider: str

    name: str | None = None

    # google specific
    email: str | None = None

    # first party specific
    app_name: str | None = None

    @field_validator("auth_provider")
    @classmethod
    def validate_auth_provider(cls, v: str) -> str:
        valid_providers = (
            [settings.FIRST_PARTY_OAUTH_PROVIDER_NAME, "google"]
            if settings.auth_enabled
            else [NO_AUTH_PROVIDER]
        )

        if v not in valid_providers:
            raise ValueError(f"Invalid auth provider: {v}")
        return v

    @model_validator(mode="after")
    def validate_user_id(self) -> "AuthUser":
        if len(self.user_id) > 54:
            raise ValueError(f"User id is too long: {self.user_id}")
        if not re.match(r"^[a-z0-9-]+$", self.user_id):
            raise ValueError(f"User id contains invalid characters: {self.user_id}")
        return self

    @property
    def user_id(self) -> str:
        """
        Unique user name combining login and auth provider.
        Only numbers, lowercase letters and dashes are allowed.
        Maximum length is 54 characters.
        """
        return f"{self.sub}-{self.auth_provider}"

    @classmethod
    def from_user_id(cls, user_id: str) -> "AuthUser":
        parts = user_id.split(".")
        if len(parts) != 2:
            raise ValueError(f"Invalid user id: {user_id}")
        return cls(sub=".".join(parts[:-1]), auth_provider=parts[-1])

    def dump(self):
        return self.model_dump(exclude_none=True, mode="json")


def get_auth_user() -> AuthUser:
    if not settings.auth_enabled:
        return _get_user_for_no_auth()

    token = get_access_token()
    if not token:
        raise RuntimeError("No auth user found")

    sub = token.claims.get("sub")
    name = token.claims.get("name")
    email = token.claims.get("email")
    app_name = token.claims.get("app_name")
    provider = token.claims.get("auth_provider")
    if not sub or not provider:
        raise RuntimeError("Missing sub or provider in auth token")

    return AuthUser(sub=sub, auth_provider=provider, name=name, email=email, app_name=app_name)


NO_AUTH_PROVIDER = "noauth"


def _get_user_for_no_auth() -> AuthUser:
    """Fake auth user for when auth is disabled to keep the code consistent."""
    hostname = socket.gethostname()
    logger.warning(f"Hostname is {hostname}")
    sub = re.sub(r"[^a-z0-9-]", "", hostname.lower().removesuffix(".local"))
    return AuthUser(sub=sub, auth_provider=NO_AUTH_PROVIDER)
