import logging
import sys
from typing import TYPE_CHECKING

import logfire
import yaml
from loguru import logger

if TYPE_CHECKING:
    from logging import LogRecord

    from loguru import Record


class InterceptHandler(logging.Handler):
    """Route stdlib logging records through Loguru."""

    def emit(self, record: "LogRecord") -> None:  # pragma: no cover - thin adapter
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _format_record(record: "Record") -> str:
    """Format log record with nice extra field formatting."""
    base = (
        "<green><level>{level: <8}</level></green>  | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "{message}\n"
    )

    extra = {k: v for k, v in record["extra"].items() if not k.startswith("_")}

    if extra:
        extra_yaml = yaml.dump(extra, sort_keys=False, default_flow_style=False).rstrip()
        return base + extra_yaml + "\n"

    return base


def setup_logging(level: str = "INFO"):
    """Configure Loguru with stderr and logfire sinks."""
    from getgather.config import settings

    log_level = (level or settings.LOG_LEVEL).upper()

    logging.basicConfig(handlers=[InterceptHandler()], level=log_level, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastmcp"):
        std_logger = logging.getLogger(name)
        std_logger.handlers = []
        std_logger.propagate = True

    logger.remove()
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

    logger.configure(handlers=handlers)  # type: ignore[arg-type]
