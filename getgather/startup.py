import httpx
import logfire
import sentry_sdk
from fastapi import FastAPI
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from getgather.config import settings
from getgather.logs import logger, setup_logging


async def check_chromefleet_health() -> None:
    if not settings.CHROMEFLEET_URL:
        logger.info("CHROMEFLEET_URL not configured, skipping health check")
        return

    health_url = f"{settings.CHROMEFLEET_URL.rstrip('/')}/health"
    logger.info(f"Checking ChromeFleet health at {health_url}")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(health_url)
            response.raise_for_status()
            logger.info(f"ChromeFleet health check passed: {response.status_code}")
    except httpx.HTTPStatusError as e:
        error_msg = (
            f"ChromeFleet health check failed with status {e.response.status_code}: {health_url}"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
    except httpx.RequestError as e:
        error_msg = f"Failed to connect to ChromeFleet at {health_url}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


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

    # Fail early if chromefleet is not healthy to reduce ambiguous errors later
    await check_chromefleet_health()
