"""Logging filters: request context and secret scrubbing."""

from __future__ import annotations

import logging
import re

from core.middleware import get_business_context, get_request_id

_BOT_TOKEN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_PHONE = re.compile(r"\+?9647\d{9}")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.business_id = get_business_context()
        return True


def scrub(text: str) -> str:
    text = _BOT_TOKEN.sub("<bot-token>", text)
    return _PHONE.sub(lambda m: m.group(0)[:7] + "*****", text)


class SecretScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub(record.msg)
        if record.args:
            record.args = tuple(scrub(a) if isinstance(a, str) else a for a in record.args)
        return True
