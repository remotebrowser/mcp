import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

import logfire
import yaml
from loguru import logger
from rich.console import Console
from rich.logging import RichHandler

if TYPE_CHECKING:
    from loguru import Record

LOGGER_NAME = "getgather"
DEBUG = "DEBUG"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_log_level(level: str) -> tuple[str, int]:
    """Return loguru and stdlib representations of the desired level."""

    normalized = level.upper()
    std_level = getattr(logging, normalized, logging.INFO)

    try:
        logger.level(normalized)
    except ValueError:
        normalized = DEBUG

    return normalized, std_level


def _clean_extra(extra: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in extra.items() if not key.startswith("_logger_")}


def _format_path_hint(path: str | Path | None) -> str:
    if not path:
        return ""

    try:
        resolved = Path(path).resolve()
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except Exception:
        return str(path)


def _escape_markup(value: str) -> str:
    return value.replace("{", "{{").replace("}", "}}").replace("<", r"\<").replace(">", r"\>")


def setup_logging(level: str = "INFO", logs_dir: Path | None = None):
    """Configure Loguru with structured logging."""
    from getgather.config import settings

    loguru_level, std_level = _resolve_log_level(level or settings.LOG_LEVEL)

    logger.remove()

    # Create Rich handler without timestamps (Loguru handles that)
    rich_handler = RichHandler(
        console=Console(stderr=True),
        show_time=False,
        show_level=False,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )

    def _format_loguru(record: "Record") -> str:
        # Format: time, level, location, message, extras
        time_fmt = "{time:HH:mm:ss}"
        level_fmt = "<level>{level: <8}</level>"
        extra = record["extra"]
        location_parts = (
            _format_path_hint(extra.get("_logger_pathname"))
            or extra.get("_logger_name")
            or record["name"],
            extra.get("_logger_func") or record["function"],
            extra.get("_logger_lineno") or record["line"],
        )
        escaped_location = tuple(_escape_markup(str(part)) for part in location_parts)
        location_fmt = (
            f"<cyan>{escaped_location[0]}:{escaped_location[1]}:{escaped_location[2]}</cyan>"
        )
        message_fmt = "<level>{message}</level>"

        base = f"{time_fmt} | {level_fmt} | {location_fmt} - {message_fmt}"

        cleaned_extra = _clean_extra(extra)
        if cleaned_extra:
            extra_yaml = yaml.dump(
                cleaned_extra, sort_keys=False, default_flow_style=False
            ).rstrip()
            extra_escaped = _escape_markup(extra_yaml)
            return f"{base}\n{extra_escaped}\n"

        return base

    handlers: list[dict] = [  # type: ignore[type-arg]
        {
            "sink": rich_handler,
            "format": _format_loguru,
            "level": loguru_level,
            "backtrace": True,
            "diagnose": True,
        }
    ]

    # Add file handler if logs_dir is provided
    if logs_dir:
        logfile = (logs_dir / "getgather.log").as_posix()
        handlers.append(  # type: ignore[arg-type]
            {
                "sink": logfile,
                "format": "{message}",
                "level": "INFO",
                "rotation": "100 MB",
                "retention": "30 days",
                "serialize": True,
                "enqueue": True,
                "backtrace": True,
                "diagnose": False,
            }
        )

    # Add Logfire handler if token is available
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
        handlers.append(logfire.loguru_handler())  # type: ignore[arg-type]

    logger.configure(handlers=handlers)  # type: ignore[arg-type]

    # Intercept standard library logging
    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            # Get corresponding Loguru level if it exists
            try:
                level_name = logger.level(record.levelname).name
            except ValueError:
                level_name = str(record.levelno)

            # Find caller from where originated the logged message
            frame, depth = logging.currentframe(), 2
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            bound_logger = logger.bind(
                _logger_name=record.name,
                _logger_pathname=_format_path_hint(record.pathname),
                _logger_func=record.funcName,
                _logger_lineno=record.lineno,
            )
            bound_logger.opt(depth=depth, exception=record.exc_info).log(
                level_name, record.getMessage()
            )

    # Override the loggers of external libraries to ensure consistent formatting
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for logger_name in (
        "uvicorn",
        "uvicorn.access",
        "uvicorn.error",
        "fastapi",
        "fastmcp",
        "sse_starlette",
    ):
        lib_logger = logging.getLogger(logger_name)
        lib_logger.handlers = [InterceptHandler()]
        lib_logger.setLevel(std_level)
        lib_logger.propagate = False
        lib_logger.setLevel(level)
