from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics import services
from core.errors import DomainError
from core.tenancy import IsBusinessMember


def _range(request: Request) -> tuple[date, date]:
    today = timezone.localdate()
    try:
        end = date.fromisoformat(request.query_params.get("to", today.isoformat()))
        start = date.fromisoformat(
            request.query_params.get("from", (end - timedelta(days=29)).isoformat())
        )
    except ValueError:
        raise DomainError("validation_error", {"from": ["YYYY-MM-DD"]}, 400) from None
    if start > end or (end - start).days > 366:
        raise DomainError("validation_error", {"range": ["max 366 days"]}, 400)
    return start, end


class _Base(APIView):
    permission_classes = [IsBusinessMember]
    required_permissions = {"get": ["reports.view"]}


class OverviewView(_Base):
    def get(self, request: Request, business_id: Any) -> Response:
        start, end = _range(request)
        data = services.overview(request.business, start, end)
        data["status_breakdown"] = services.status_breakdown(request.business, start, end)
        return Response(data)


class SalesView(_Base):
    def get(self, request: Request, business_id: Any) -> Response:
        start, end = _range(request)
        interval = request.query_params.get("interval", "day")
        if interval not in ("day", "week", "month"):
            raise DomainError("validation_error", {"interval": ["day|week|month"]}, 400)
        return Response(services.sales_series(request.business, start, end, interval))


class TopProductsView(_Base):
    def get(self, request: Request, business_id: Any) -> Response:
        start, end = _range(request)
        return Response(services.top_products(request.business, start, end))


class RecentCustomersView(_Base):
    required_permissions = {"get": ["customers.view"]}

    def get(self, request: Request, business_id: Any) -> Response:
        return Response(services.recent_customers(request.business))
