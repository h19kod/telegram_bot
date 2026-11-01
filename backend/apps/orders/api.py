from __future__ import annotations

import csv
import io
from typing import Any

from django.db.models import Count
from django.http import HttpResponse
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.orders.models import EventSource, Order, OrderStatus
from apps.orders.serializers import OrderDetailSerializer, OrderListSerializer, TransitionSerializer
from apps.orders.services.transitions import assign_driver, transition
from apps.staff.models import Membership
from apps.subscriptions.services import require_feature
from core.errors import NotFoundError
from core.phone import normalize_phone
from core.tenancy import IsBusinessMember, require
from core.text import to_latin_digits


class OrderFilter(filters.FilterSet):
    status = filters.MultipleChoiceFilter(choices=OrderStatus.choices)
    placed_after = filters.IsoDateTimeFilter(field_name="placed_at", lookup_expr="gte")
    placed_before = filters.IsoDateTimeFilter(field_name="placed_at", lookup_expr="lt")
    customer = filters.UUIDFilter(field_name="customer_id")
    fulfilment = filters.ChoiceFilter(choices=[("delivery", "delivery"), ("pickup", "pickup")])
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = Order
        fields = ["status", "fulfilment", "channel", "customer", "assigned_driver"]

    def filter_search(self, qs, name, value):  # type: ignore[no-untyped-def]
        value = to_latin_digits(value.strip().lstrip("#"))
        if value.isdigit() and len(value) <= 9:
            return qs.filter(number=int(value))
        try:
            return qs.filter(customer_phone=normalize_phone(value))
        except ValueError:
            return qs.filter(customer_name__icontains=value)


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsBusinessMember]
    required_permissions = {"*": ["orders.view"]}
    filterset_class = OrderFilter
    ordering_fields = ["placed_at", "total", "number"]
    ordering = ["-placed_at"]

    def get_serializer_class(self):  # type: ignore[no-untyped-def]
        return OrderListSerializer if self.action == "list" else OrderDetailSerializer

    def get_queryset(self):  # type: ignore[no-untyped-def]
        qs = Order.objects.for_business(self.request.business)
        m: Membership = self.request.membership
        if m.has_perm("orders.view_assigned_only"):
            qs = qs.filter(assigned_driver=m)
        if self.action == "list":
            return qs.annotate(items_count=Count("items"))
        return qs.select_related("business__settings").prefetch_related(
            "items__options", "events__actor_user"
        )

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        m = getattr(self.request, "membership", None)
        ctx["membership"] = m
        ctx["show_pii"] = bool(m and m.has_perm("customers.view_pii"))
        return ctx

    @extend_schema(request=TransitionSerializer, responses=OrderDetailSerializer)
    @action(detail=True, methods=["post"])
    def transition(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        s = TransitionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        result = transition(
            business_id=request.business.id,
            order_id=pk,
            to=s.validated_data["to"],
            source=EventSource.DASHBOARD,
            membership=request.membership,
            expected_version=s.validated_data.get("expected_version"),
            reason=s.validated_data.get("reason", ""),
        )
        order = self.get_queryset().get(pk=result.order.pk)
        data = OrderDetailSerializer(order, context=self.get_serializer_context()).data
        return Response({**data, "applied": result.applied})

    @action(detail=True, methods=["post"], url_path="assign-driver")
    def assign(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        order = self.get_object()
        driver_id = serializers.UUIDField(allow_null=True).run_validation(
            request.data.get("driver_id")
        )
        driver = None
        if driver_id:
            driver = (
                Membership.objects.for_business(request.business)
                .filter(id=driver_id, is_active=True)
                .first()
            )
            if driver is None:
                raise NotFoundError({"driver_id": str(driver_id)})
        assign_driver(order, driver, request.membership)
        return Response(
            OrderDetailSerializer(
                self.get_queryset().get(pk=order.pk), context=self.get_serializer_context()
            ).data
        )

    @action(detail=False, methods=["get"])
    def export(self, request: Request, business_id: Any) -> HttpResponse:
        require(request, "reports.export")
        require_feature(request.business.id, "analytics_export")
        qs = self.filter_queryset(self.get_queryset()).order_by("-placed_at")[:20000]
        fmt = request.query_params.get("format_type", "csv")
        headers = [
            "number",
            "placed_at",
            "status",
            "fulfilment",
            "customer_name",
            "customer_phone",
            "zone",
            "subtotal",
            "delivery_fee",
            "discount",
            "total",
            "currency",
            "payment_method",
            "channel",
        ]
        show_pii = request.membership.has_perm("customers.view_pii")
        rows = [
            [
                o.number,
                o.placed_at.isoformat(),
                o.status,
                o.fulfilment,
                o.customer_name,
                o.customer_phone if show_pii else "",
                o.zone_name_snapshot,
                o.subtotal,
                o.delivery_fee,
                o.discount_total,
                o.total,
                o.currency,
                o.payment_method,
                o.channel,
            ]
            for o in qs
        ]
        if fmt == "xlsx":
            from openpyxl import Workbook

            wb = Workbook()
            ws = wb.active
            ws.append(headers)
            for r in rows:
                ws.append([_safe_cell(c) for c in r])
            buf = io.BytesIO()
            wb.save(buf)
            resp = HttpResponse(
                buf.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            resp["Content-Disposition"] = 'attachment; filename="orders.xlsx"'
            return resp
        out = io.StringIO()
        out.write("﻿")  # BOM so Excel opens Arabic correctly
        writer = csv.writer(out)
        writer.writerow(headers)
        writer.writerows([[_safe_cell(c) for c in r] for r in rows])
        resp = HttpResponse(out.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="orders.csv"'
        return resp


def _safe_cell(value: Any) -> Any:
    """Neutralise spreadsheet formula injection in user-supplied text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value
