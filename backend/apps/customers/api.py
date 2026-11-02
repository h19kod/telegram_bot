from __future__ import annotations

from typing import Any

from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.customers.models import Customer, LoyaltyEntry
from apps.orders.services import loyalty
from apps.platform_admin.audit import audit
from core.phone import mask_phone
from core.tenancy import IsBusinessMember, require


class CustomerSerializer(serializers.ModelSerializer):
    phone = serializers.SerializerMethodField()
    display_name = serializers.CharField(read_only=True)
    phone_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "display_name",
            "full_name",
            "first_name",
            "last_name",
            "telegram_username",
            "phone",
            "phone_verified",
            "points_balance",
            "language",
            "is_blocked",
            "blocked_reason",
            "orders_count",
            "total_spent",
            "first_order_at",
            "last_order_at",
            "created_at",
        ]

    def get_phone(self, obj: Customer) -> str:
        return obj.phone if self.context.get("show_pii") else mask_phone(obj.phone)


class LoyaltyEntrySerializer(serializers.ModelSerializer):
    order_number = serializers.IntegerField(source="order.number", read_only=True, allow_null=True)

    class Meta:
        model = LoyaltyEntry
        fields = ["id", "delta", "reason", "balance_after", "note", "order_number", "created_at"]
        read_only_fields = fields


class PointsAdjustSerializer(serializers.Serializer):
    delta = serializers.IntegerField(min_value=-100000, max_value=100000)
    note = serializers.CharField(max_length=200)


class CustomerFilter(filters.FilterSet):
    search = filters.CharFilter(method="filter_search")
    is_blocked = filters.BooleanFilter()

    class Meta:
        model = Customer
        fields = ["is_blocked", "language"]

    def filter_search(self, qs, name, value):  # type: ignore[no-untyped-def]
        from django.db.models import Q

        from core.text import to_latin_digits

        v = to_latin_digits(value.strip())
        return qs.filter(
            Q(full_name__icontains=v)
            | Q(first_name__icontains=v)
            | Q(telegram_username__icontains=v.lstrip("@"))
            | Q(phone__contains=v.lstrip("0"))
        )


class CustomerViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsBusinessMember]
    required_permissions = {"*": ["customers.view"]}
    serializer_class = CustomerSerializer
    filterset_class = CustomerFilter
    ordering_fields = ["last_order_at", "orders_count", "total_spent", "created_at"]
    ordering = ["-last_order_at"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return Customer.objects.for_business(getattr(self.request, "business", None))

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        m = getattr(self.request, "membership", None)
        ctx["show_pii"] = bool(m and m.has_perm("customers.view_pii"))
        return ctx

    @action(detail=True, methods=["post"])
    def block(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        require(request, "customers.block")
        c = self.get_object()
        c.is_blocked = True
        c.blocked_reason = str(request.data.get("reason", ""))[:200]
        c.save(update_fields=["is_blocked", "blocked_reason", "updated_at"])
        audit(request, "customer.block", request.business, c, {"reason": c.blocked_reason})
        return Response(self.get_serializer(c).data)

    @action(detail=True, methods=["post"])
    def unblock(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        require(request, "customers.block")
        c = self.get_object()
        c.is_blocked, c.blocked_reason = False, ""
        c.save(update_fields=["is_blocked", "blocked_reason", "updated_at"])
        audit(request, "customer.unblock", request.business, c)
        return Response(self.get_serializer(c).data)

    @extend_schema(responses=LoyaltyEntrySerializer(many=True))
    @action(detail=True, methods=["get"])
    def points(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        c = self.get_object()
        entries = LoyaltyEntry.objects.for_business(request.business).filter(customer=c)
        return Response(
            LoyaltyEntrySerializer(entries.select_related("order")[:100], many=True).data
        )

    @extend_schema(request=PointsAdjustSerializer, responses=CustomerSerializer)
    @points.mapping.post
    def adjust_points(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        require(request, "settings.edit")
        c = self.get_object()
        s = PointsAdjustSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        entry = loyalty.adjust(c, s.validated_data["delta"], s.validated_data["note"])
        audit(
            request,
            "customer.points_adjust",
            request.business,
            c,
            {"delta": entry.delta, "note": entry.note},
        )
        c.refresh_from_db()
        return Response(self.get_serializer(c).data)
