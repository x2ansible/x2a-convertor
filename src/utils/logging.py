import os
import logging
import sys
import structlog

from langchain.globals import set_debug

logger = structlog.get_logger(__name__)

SILENT_LOGGERS = ["openai.", "langchain_openai.", "httpcore.", "httpx."]


def mute_unrelated_logging():
    """
    Make logging less verbose for selected loggers but preserve others.
    When LANGCHAIN_DEBUG env variable is not set, we only want to see errors
    and warnings for its related modules.
    We can not set that in app.py because the loggers are not created yet.
    """
    langchain_debug = os.environ.get("LANGCHAIN_DEBUG", "FALSE").upper()
    if langchain_debug == "TRUE":
        # keep verbose logging
        return

    logger.warning(
        f"Silencing unnecessary / very verbose logging from: {SILENT_LOGGERS}"
    )
    for log_name, _ in logging.Logger.manager.loggerDict.items():
        for silent in SILENT_LOGGERS:
            if log_name.startswith(silent):
                logging.getLogger(log_name).setLevel(logging.INFO)


def format_context(logger, method_name, event_dict):
    """Format bound context into the event message"""
    excluded = {"level", "timestamp", "logger", "stack", "exc_info", "event"}
    context = " ".join(f"{k}={v}" for k, v in event_dict.items() if k not in excluded)

    event = event_dict.get("event", "")
    event_dict["event"] = f"{event} [{context}]" if context else event

    return event_dict


def setup_logging() -> None:
    """Setup logging for the application"""
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    langchain_debug = os.environ.get("LANGCHAIN_DEBUG", "FALSE").upper()

    logging.basicConfig(
        stream=sys.stderr, level=log_level, format="%(levelname)s:%(name)s: %(message)s"
    )

    if langchain_debug == "TRUE":
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
