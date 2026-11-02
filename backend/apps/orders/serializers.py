from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.orders.models import (
    Fulfilment,
    Order,
    OrderItem,
    OrderItemOption,
    OrderStatus,
    OrderStatusEvent,
)
from apps.orders.services.cart import PricedCart
from core.phone import mask_phone
from core.serializers import current_lang


class OrderItemOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItemOption
        fields = [
            "group_name_ar",
            "group_name_en",
            "option_name_ar",
            "option_name_en",
            "price_delta",
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    options = OrderItemOptionSerializer(many=True, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name_ar",
            "product_name_en",
            "unit_price",
            "quantity",
            "line_total",
            "note",
            "options",
        ]


class OrderEventSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = OrderStatusEvent
        fields = ["from_status", "to_status", "source", "reason", "actor", "created_at"]

    def get_actor(self, obj: OrderStatusEvent) -> str:
        if obj.actor_user_id:
            return obj.actor_user.full_name or str(obj.actor_user)
        return ""


class OrderListSerializer(serializers.ModelSerializer):
    customer_phone = serializers.SerializerMethodField()
    items_count = serializers.IntegerField(
        read_only=True, default=None, allow_null=True, help_text="List only; null in detail"
    )

    class Meta:
        model = Order
        fields = [
            "id",
            "number",
            "status",
            "version",
            "fulfilment",
            "channel",
            "customer",
            "customer_name",
            "customer_phone",
            "zone_name_snapshot",
            "table_label",
            "currency",
            "subtotal",
            "delivery_fee",
            "discount_total",
            "total",
            "payment_method",
            "payment_status",
            "placed_at",
            "assigned_driver",
            "items_count",
        ]

    def get_customer_phone(self, obj: Order) -> str:
        if self.context.get("show_pii"):
            return obj.customer_phone
        return mask_phone(obj.customer_phone)


class OrderDetailSerializer(OrderListSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    events = OrderEventSerializer(many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()

    class Meta(OrderListSerializer.Meta):
        fields = [
            *OrderListSerializer.Meta.fields,
            "notes",
            "address",
            "latitude",
            "longitude",
            "cancel_reason",
            "confirmed_at",
            "ready_at",
            "delivered_at",
            "cancelled_at",
            "items",
            "events",
            "allowed_actions",
            "branch",
        ]

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(choices=OrderStatus.choices))
    )
    def get_allowed_actions(self, obj: Order) -> list[str]:
        from apps.orders.services.transitions import actions_for

        return actions_for(obj, self.context.get("membership"))

    @extend_schema_field(
        serializers.DictField(
            child=serializers.CharField(),
            allow_null=True,
            help_text="Delivery only; without customers.view_pii just {zone}",
        )
    )
    def get_address(self, obj: Order) -> dict[str, str] | None:
        if obj.fulfilment != "delivery":
            return None
        if not self.context.get("show_pii"):
            return {"zone": obj.zone_name_snapshot}
        return {
            "zone": obj.zone_name_snapshot,
            "area": obj.address_area,
            "street": obj.address_street,
            "landmark": obj.address_landmark,
            "building": obj.address_building,
        }


class TransitionSerializer(serializers.Serializer):
    to = serializers.CharField(max_length=20)
    expected_version = serializers.IntegerField(required=False, min_value=1)
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True)


def priced_cart_data(priced: PricedCart) -> dict[str, Any]:
    from core.models import localized

    lang = current_lang()
    lines = []
    for line in priced.lines:
        p = line.item.product
        img = p.images.all()[0] if p.images.all() else None
        lines.append(
            {
                "id": str(line.item.id),
                "product_id": str(p.id),
                "name": localized(p, "name", lang),
                "image": img.thumbnail.url if img and img.thumbnail else None,
                "options": [
                    {
                        "id": str(o.id),
                        "name": localized(o, "name", lang),
                        "price_delta": o.price_delta,
                    }
                    for o in line.options
                ],
                "quantity": line.item.quantity,
                "note": line.item.note,
                "unit_price": line.unit_price,
                "line_total": line.line_total,
                "available": line.available,
                "warning": line.warning,
            }
        )
    currency = priced.cart.business.currency if priced.cart else None
    return {
        "lines": lines,
        "subtotal": priced.subtotal,
        "item_count": priced.item_count,
        "has_problems": priced.has_problems,
        "currency": currency,
    }


class CheckoutSerializer(serializers.Serializer):
    fulfilment = serializers.ChoiceField(choices=Fulfilment.choices)
    customer_name = serializers.CharField(max_length=150)
    customer_phone = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
        help_text="Required except for dine_in",
    )
    zone_id = serializers.UUIDField(required=False, allow_null=True)
    table_label = serializers.CharField(
        max_length=10, required=False, allow_blank=True, help_text="dine_in: table number"
    )
    address_area = serializers.CharField(max_length=120, required=False, allow_blank=True)
    address_street = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_landmark = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_building = serializers.CharField(max_length=120, required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True, min_value=-90, max_value=90
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
        min_value=-180,
        max_value=180,
    )
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    coupon_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    payment_method = serializers.CharField(max_length=32, required=False, allow_blank=True)


class QuoteSerializer(CheckoutSerializer):
    """Quotes price the cart before contact details are entered."""

    customer_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    customer_phone = serializers.CharField(
        max_length=32, required=False, allow_blank=True, default=""
    )


def quote_data(q: Any) -> dict[str, Any]:
    return {
        "subtotal": q.subtotal,
        "delivery_fee": q.delivery_fee,
        "discount_total": q.discount_total,
        "total": q.total,
        "currency": q.currency,
        "payment_method": q.payment_method,
        "coupon": {"code": q.coupon.code, "discount": q.discount_total} if q.coupon else None,
        "zone": {
            "id": str(q.zone.id),
            "name_ar": q.zone.name_ar,
            "name_en": q.zone.name_en,
            "eta_min": q.zone.eta_min,
            "eta_max": q.zone.eta_max,
        }
        if q.zone
        else None,
    }
