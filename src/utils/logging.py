import os
import logging
import sys
import structlog

from langchain.globals import set_debug


def get_logger(name: str | None = None):
    """
    Get a logger with x2convertor prefix.

    Args:
        name: Module name (typically __name__). If None, returns root x2convertor logger.

    Returns:
        A structlog logger with x2convertor prefix.
    """
    if name is None:
        return structlog.get_logger("x2convertor")
    return structlog.get_logger(f"x2convertor.{name}")


logger = get_logger(__name__)


def setup_third_party_logging(debug_all: bool = False):
    """
    Configure third-party library logging levels.

    Args:
        debug_all: If True, enable verbose logging for all libraries.
                   If False, set third-party loggers to WARNING level.
    """

    if debug_all:
        return

    # Also set any existing child loggers to warning
    for log_name, _ in logging.Logger.manager.loggerDict.items():
        logging.getLogger(log_name).setLevel(logging.WARNING)


def format_context(logger, method_name, event_dict):
    """Format bound context into the event message"""
    excluded = {"level", "timestamp", "logger", "stack", "exc_info", "event"}
    context = " ".join(f"{k}={v}" for k, v in event_dict.items() if k not in excluded)

    event = event_dict.get("event", "")
    event_dict["event"] = f"{event} [{context}]" if context else event

    return event_dict


def setup_logging() -> None:
    """
    Setup logging for the application.

    Environment variables:
        DEBUG_ALL: If set to "true" (case-insensitive), enable DEBUG logging for all libraries.
                   If not set, x2convertor logs at INFO, third-party libraries at WARNING.
    """
    debug_all = os.environ.get("DEBUG_ALL", "false").lower() == "true"
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Root logger level - WARNING by default, DEBUG only if DEBUG_ALL is set
    root_level = "DEBUG" if debug_all else "WARNING"
    logging.basicConfig(
        stream=sys.stderr,
        level=root_level,
        format="%(levelname)s:%(name)s: %(message)s"
    )

    # Configure LangChain debug mode
    if debug_all:
        set_debug(True)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            format_context,
            structlog.stdlib.render_to_log_kwargs,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Suppress third-party loggers unless DEBUG_ALL is set
    setup_third_party_logging(debug_all)

    # x2convertor logs: use LOG_LEVEL if set, otherwise DEBUG if DEBUG_ALL, otherwise INFO
    logging.getLogger("x2convertor").setLevel(log_level)
