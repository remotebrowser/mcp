import logging
from typing import TYPE_CHECKING

import logfire
import sentry_sdk
import yaml
from fastapi import FastAPI
from loguru import logger
from rich.logging import RichHandler
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

if TYPE_CHECKING:
    from loguru import HandlerConfig, Record

from getgather.config import settings


def instrument_fastapi(app: FastAPI):
    if not settings.LOGFIRE_TOKEN:
        return
    logfire.instrument_fastapi(app, capture_headers=True, excluded_urls="/health")


def setup_logging():
    _setup_logfire()
    _setup_logger()
    _setup_sentry()


def _setup_logfire():
    if not settings.LOGFIRE_TOKEN:
        logger.warning("Logfire is disabled, no LOGFIRE_TOKEN provided")
        return

    logger.info("Initializing Logfire")
    logfire.configure(
        service_name="mcp-getgather",
        send_to_logfire="if-token-present",
        token=settings.LOGFIRE_TOKEN,
        environment=settings.ENVIRONMENT,
        min_level=logging.getLevelNamesMapping()[settings.LOG_LEVEL],
        code_source=logfire.CodeSource(
            repository="https://github.com/remotebrowser/mcp-getgather", revision="main"
        ),
        console=False,
        scrubbing=False,
    )


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

    if settings.LOGFIRE_TOKEN:
        handlers.append(logfire.loguru_handler())

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
