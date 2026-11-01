"""Request id propagation (logs, error bodies, Sentry)."""

from __future__ import annotations

import contextvars
import re
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from uuid6 import uuid7

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_business_id: contextvars.ContextVar[str] = contextvars.ContextVar("business_id", default="-")
_VALID_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


def get_request_id() -> str:
    return _request_id.get()


def set_business_context(business_id: object) -> None:
    _business_id.set(str(business_id))


def get_business_context() -> str:
    return _business_id.get()


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _VALID_ID.match(incoming) else str(uuid7())
        token = _request_id.set(rid)
        btoken = _business_id.set("-")
        try:
            response = self.get_response(request)
        finally:
            _request_id.reset(token)
            _business_id.reset(btoken)
        response["X-Request-ID"] = rid
        return response
