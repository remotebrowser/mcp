import sys
from typing import TYPE_CHECKING

import logfire
import yaml
from loguru import logger

if TYPE_CHECKING:
    from loguru import Record


def _format_record(record: "Record") -> str:
    """Format log record with nice extra field formatting."""
    # Base format
    base = (
        "<green><level>{level: <8}</level></green>  | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "{message}\n"
    )

    # Get extra fields, excluding loguru internals
    extra = {k: v for k, v in record["extra"].items() if not k.startswith("_")}

    if extra:
        # Format extra fields as YAML
        extra_yaml = yaml.dump(extra, sort_keys=False, default_flow_style=False).rstrip()
        return base + extra_yaml + "\n"

    return base


def setup_logging(level: str = "INFO"):
    """Configure Loguru with stderr and logfire sinks."""
    from getgather.config import settings

    log_level = (level or settings.LOG_LEVEL).upper()

    # Remove default handler
    logger.remove()
    # Build handler configurations
    handlers = [
        {
            "sink": sys.stderr,
            "level": log_level,
            "format": _format_record,
            "colorize": True,
            "backtrace": True,
            "diagnose": True,
        }
    ]

    # Add logfire handler if token is available
    if settings.LOGFIRE_TOKEN:
        logfire.configure(
            service_name="mcp-getgather",
            send_to_logfire="if-token-present",
            token=settings.LOGFIRE_TOKEN,
            environment=settings.ENVIRONMENT,
            distributed_tracing=True,
            code_source=logfire.CodeSource(
                repository="https://github.com/remotebrowser/mcp-getgather", revision="main"
            ),
            console=False,
            scrubbing=False,
        )
        handlers.append(logfire.loguru_handler())

    # Configure all handlers
    logger.configure(handlers=handlers)
