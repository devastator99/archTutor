"""Structured logging.

Deliberately the standard library. The requirement is "log validation duration,
API errors, AI latency, AI failures, exercise completion" and not "add
observability infrastructure". A logging framework, an exporter and a dashboard
would be three dependencies and a deployment to answer a question that five log
lines already answer.

ONE LINE PER EVENT, JSON, ONE WRITE
----------------------------------
Each event is a single JSON object on a single line. That is what makes it
greppable by event name and countable without a parser, and it is the format
every log shipper already understands. The alternative -- pretty multi-line
console output -- reads better in a terminal and cannot be counted at all.

WHAT IS NEVER LOGGED
--------------------
Findings contain a student's drawing measurements, and requests contain
geometry. Neither is logged. Only identifiers, counts, durations and event
names. A student's work is not an operational log line, and a log is not the
place to keep a copy of it.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator

LOGGER_NAME = "archtutor"

_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON handler once. Safe to call repeatedly."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger(LOGGER_NAME)
    root.handlers = [handler]
    root.setLevel(level.upper())
    # The tutor talks to an HTTP API; a debug log of its request body would put
    # the API key in the log file.
    root.propagate = False
    _configured = True


def get_logger(suffix: str | None = None) -> logging.Logger:
    configure_logging()
    return logging.getLogger(
        LOGGER_NAME if not suffix else f"{LOGGER_NAME}.{suffix}"
    )


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "event": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            # The type, not the traceback: enough to find the failure, and it
            # cannot carry a student's geometry into a log file.
            payload["error"] = record.exc_info[0].__name__ if record.exc_info[0] else "?"
        return json.dumps(payload, default=_fallback, sort_keys=True)


def _fallback(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit one structured event.

    ``event`` is a stable snake_case name, because these names are what the log
    is queried by. A free-text message would be unqueryable, which defeats the
    purpose of asking for logs at all.
    """
    logger.log(level, event, extra={"fields": _clean(fields)})


def _clean(fields: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values so an event is not padded with absent fields."""
    return {key: value for key, value in fields.items() if value is not None}


@contextmanager
def timed(logger: logging.Logger, event: str, **fields: Any) -> Iterator[dict]:
    """Time a block and log its duration, including when it raises.

    A timer that only logs on success cannot report the slow failure, which is
    usually the interesting one. The duration is emitted with ``ok=false`` and
    the exception type, then the exception propagates untouched.
    """
    started = time.perf_counter()
    outcome: dict[str, Any] = {"ok": True}
    try:
        yield outcome
    except Exception as exc:  # noqa: BLE001 - re-raised immediately
        outcome["ok"] = False
        outcome["error"] = type(exc).__name__
        log_event(
            logger,
            event,
            level=logging.ERROR,
            duration_ms=_elapsed_ms(started),
            **fields,
            **{k: v for k, v in outcome.items() if k != "ok"},
        )
        raise
    log_event(logger, event, duration_ms=_elapsed_ms(started), **fields)


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
