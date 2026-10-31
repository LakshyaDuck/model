"""Keep live credentials out of the logs.

Three facts force this:

  * tusd sends no custom headers, so HOOK_SECRET travels in the -hooks-http URL and
    arrives as ``/internal/tusd-hook?secret=...`` on every hook call.
  * EventSource and media tags cannot set headers, so the owner token arrives as
    ``?token=...`` on the events/file/thumb endpoints.
  * the phone's pair token is a URL path segment (``/m/<token>``, ``/api/pair/<token>``).

uvicorn's access log prints the full path including the query, so without this every
one of those secrets is written to stdout on each request. Redacting here means a log
aggregator (or a screenshot of a container's logs) never leaks a usable credential.
"""

from __future__ import annotations

import logging
import re

_BACKEND_HANDLER_MARKER = "_namma_backend_handler"

_REDACTIONS = (
    (re.compile(r"(secret=)[^&\s\"']+"), r"\1REDACTED"),
    (re.compile(r"(token=)[^&\s\"']+"), r"\1REDACTED"),
    (re.compile(r"(/api/pair/)[^/?\s\"']+"), r"\1REDACTED"),
    (re.compile(r"(/m/)[^/?\s\"']+"), r"\1REDACTED"),
)


def redact(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                redact(value) if isinstance(value, str) else value for value in record.args
            )
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        return True


def _configure_backend_logger() -> None:
    """Give ``backend.*`` records a visible handler under uvicorn.

    uvicorn configures only its own loggers, so application INFO records would
    otherwise fall through to logging's last-resort handler and only show warnings
    and errors. Stage progress needs the INFO records too.
    """
    logger = logging.getLogger("backend")
    if any(getattr(handler, _BACKEND_HANDLER_MARKER, False) for handler in logger.handlers):
        return
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    setattr(handler, _BACKEND_HANDLER_MARKER, True)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def install() -> None:
    """Idempotent; safe to call once per process at app creation."""
    filt = RedactingFilter()
    for name in ("uvicorn.access", "uvicorn.error", "backend", ""):
        logger = logging.getLogger(name)
        if not any(isinstance(existing, RedactingFilter) for existing in logger.filters):
            logger.addFilter(filt)
    _configure_backend_logger()
