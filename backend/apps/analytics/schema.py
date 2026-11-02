"""OpenAPI shapes of the analytics responses (built as dicts by services; checked in tests)."""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, inline_serializer
from rest_framework import serializers

RANGE_PARAMS = [
    OpenApiParameter("from", OpenApiTypes.DATE, description="Default: 29 days before `to`"),
    OpenApiParameter("to", OpenApiTypes.DATE, description="Default: today; max range 366 days"),
]


# "from" is a Python keyword, so this one is declared from a dict.
DATE_RANGE = inline_serializer(
    "DateRange", {"from": serializers.DateField(), "to": serializers.DateField()}
)


class OverviewSerializer(serializers.Serializer):
    range = DATE_RANGE
    currency = serializers.CharField()
    total_orders = serializers.IntegerField()
    completed_orders = serializers.IntegerField()
    cancelled_orders = serializers.IntegerField()
    total_sales = serializers.IntegerField(help_text="Minor units")
    average_order_value = serializers.IntegerField()
    today_orders = serializers.IntegerField()
    today_sales = serializers.IntegerField()
    pending_orders = serializers.IntegerField()
    open_orders = serializers.IntegerField()
    new_customers = serializers.IntegerField()
    status_breakdown = serializers.DictField(child=serializers.IntegerField())


class SalesPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    orders = serializers.IntegerField()
    sales = serializers.IntegerField()


class TopProductSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(allow_null=True)
    name_ar = serializers.CharField()
    name_en = serializers.CharField()
    quantity = serializers.IntegerField()
    revenue = serializers.IntegerField()


class RecentCustomerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    orders_count = serializers.IntegerField()
    total_spent = serializers.IntegerField()
    last_order_at = serializers.DateTimeField(allow_null=True)
