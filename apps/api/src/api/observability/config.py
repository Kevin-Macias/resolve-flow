"""Supported server logging: stdout JSON, including sanitized dependency records."""

import logging
import logging.config
from datetime import UTC, datetime

from pydantic import ValidationError

from api.observability import Event, context


class SafeJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        value = getattr(record, "safe_event", None)
        if record.name == "resolveflow.events" and isinstance(value, Event):
            try:
                return Event.model_validate(value.model_dump()).model_dump_json(
                    exclude_none=True
                )
            except ValidationError:
                pass
        # Never call getMessage()/formatException() on arbitrary SDK/server records.
        # Those can contain URLs, SQL parameters, provider content, or credentials.
        return Event(
            timestamp=datetime.now(UTC),
            level="ERROR"
            if record.levelno >= logging.ERROR
            else "WARNING"
            if record.levelno >= logging.WARNING
            else "INFO",
            event="runtime.error"
            if record.levelno >= logging.ERROR
            else "runtime.message",
            **context.get().model_dump(),
        ).model_dump_json(exclude_none=True)


LOG_CONFIG: dict[str, object] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"safe": {"()": "api.observability.config.SafeJSONFormatter"}},
    "handlers": {
        "json": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "safe",
        }
    },
    "root": {"handlers": ["json"], "level": "WARNING"},
    "loggers": {
        "resolveflow.events": {
            "handlers": ["json"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn": {"handlers": ["json"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": [], "level": "INFO", "propagate": True},
        "uvicorn.access": {"handlers": [], "level": "CRITICAL", "propagate": False},
        **{
            name: {"handlers": [], "level": "WARNING", "propagate": True}
            for name in (
                "openai",
                "httpx",
                "httpcore",
                "sqlalchemy",
                "psycopg",
                "langgraph",
                "langchain",
                "langsmith",
                "py.warnings",
            )
        },
    },
}


def configure_logging() -> None:
    logging.raiseExceptions = False
    logging.config.dictConfig(LOG_CONFIG)
    logging.captureWarnings(True)
