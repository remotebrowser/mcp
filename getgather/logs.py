import logging
from typing import TYPE_CHECKING

import sentry_sdk
import yaml
from fastapi import Request
from loguru import logger
from rich.logging import RichHandler
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from starlette.types import ASGIApp, Receive, Scope, Send

if TYPE_CHECKING:
    from loguru import HandlerConfig, Record

from getgather.config import settings
from getgather.tracing import logfire_loguru_handler, setup_logfire, setup_mcp_tracing


def setup_logging():
    setup_logfire()
    _setup_logger()
    _setup_sentry()


def _setup_logger():
    logger.remove()

    rich_handler = RichHandler(rich_tracebacks=True, log_time_format="%X", markup=True)

    def _format_with_extra(record: "Record") -> str:
        message = record["message"]

        if record["extra"]:
            extra = yaml.dump(record["extra"], sort_keys=False, default_flow_style=False)
            message = f"{message}\n{extra}"

        return message.replace("[", r"\[").replace("{", "{{").replace("}", "}}").replace("<", r"\<")

    handlers: list[HandlerConfig] = [
        {
            "sink": rich_handler,
            "format": _format_with_extra,
            "level": settings.LOG_LEVEL,
            "backtrace": True,
            "diagnose": True,
        }
    ]

    logfire_handler = logfire_loguru_handler()
    if logfire_handler is not None:
        handlers.append(logfire_handler)

    logger.configure(handlers=handlers)

    # Override the loggers of external libraries to ensure consistent formatting
    for logger_name in (
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastmcp",
        "fastmcp.server",
        "fastmcp.fastmcp.server.auth.oauth_proxy",
        "fastmcp.fastmcp.server.auth.providers.github",
        "fastmcp.fastmcp.server.auth.providers.google",
    ):
        lib_logger = logging.getLogger(logger_name)
        lib_logger.handlers.clear()  # Remove existing handlers
        lib_logger.addHandler(rich_handler)
        lib_logger.propagate = False


def _setup_sentry():
    if not settings.SENTRY_DSN:
        logger.warning("Sentry is disabled, no SENTRY_DSN provided")
        return

    logger.info("Initializing Sentry")
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[
            StarletteIntegration(
                transaction_style="endpoint",
                failed_request_status_codes={403, *range(500, 599)},
            ),
            FastApiIntegration(
                transaction_style="endpoint",
                failed_request_status_codes={403, *range(500, 599)},
            ),
            LoggingIntegration(level=logging.getLevelNamesMapping()[settings.LOG_LEVEL]),
        ],
        send_default_pii=True,
    )


class MCPLoggingContextMiddleware:
    """Raw ASGI middleware that attaches per-request MCP identifiers to loguru's
    contextvars so downstream logs carry `mcp_session_id`."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        mcp_session_id = setup_mcp_tracing(request)

        context: dict[str, str] = {"mcp_session_id": mcp_session_id}
        with logger.contextualize(**context):
            logger.info(f"[MIDDLEWARE] Processing MCP request to {scope['path']}")
            await self.app(scope, receive, send)
