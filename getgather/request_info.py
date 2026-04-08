from contextvars import ContextVar

from pydantic import BaseModel, Field


class RequestInfo(BaseModel):
    """Information about the request that initiated the auth flow."""

    proxy_type: str | None = Field(
        description="The proxy type to use (e.g., 'proxy-0', 'proxy-1')", default=None
    )


request_info: ContextVar[RequestInfo | None] = ContextVar("request_info", default=None)
