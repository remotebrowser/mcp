from contextvars import ContextVar

from pydantic import BaseModel, Field


class RequestInfo(BaseModel):
    """Information about the request that initiated the auth flow."""

    city: str | None = Field(description="The city of the client.", default=None)
    state: str | None = Field(description="The state of the client.", default=None)
    country: str | None = Field(description="The country of the client.", default=None)
    postal_code: str | None = Field(description="The postal code of the client.", default=None)
    timezone: str | None = Field(description="The timezone of the client.", default=None)
    proxy_type: str | None = Field(
        description="The proxy type to use (e.g., 'proxy-0', 'proxy-1')", default=None
    )


request_info: ContextVar[RequestInfo | None] = ContextVar("request_info", default=None)
