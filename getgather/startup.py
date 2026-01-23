import logfire
import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from getgather.config import settings
from getgather.logs import logger, setup_logging


async def startup(app: FastAPI | None = None):
    # Setup logging first
    setup_logging(level=settings.LOG_LEVEL)

    logger.info("Setting up Logfire and Sentry with LOG_LEVEL=%s", settings.LOG_LEVEL)

    # Instrument FastAPI if app is provided and Logfire is configured
    if app and settings.LOGFIRE_TOKEN:
        logfire.instrument_fastapi(app, capture_headers=True)

    # Setup Sentry
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
        ],
        send_default_pii=True,
    )
