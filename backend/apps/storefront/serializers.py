"""Customer-facing catalog representations (shared by the Mini App and the bot)."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.businesses.models import Branch, Business
from apps.businesses.services import is_open
from apps.categories.models import Category
from apps.delivery.models import DeliveryZone
from apps.orders.models import Order, OrderStatus
from apps.products.models import Option, OptionGroup, Product
from core.serializers import LocalizedField


def _url(f: Any) -> str | None:
    return f.url if f else None


class StoreImageSerializer(serializers.Serializer):
    url = serializers.URLField(allow_null=True)
    thumbnail = serializers.URLField(allow_null=True)
    width = serializers.IntegerField()
    height = serializers.IntegerField()


class StoreOrderItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.IntegerField()
    line_total = serializers.IntegerField()
    note = serializers.CharField()
    product_id = serializers.UUIDField(allow_null=True)
    options = serializers.ListField(child=serializers.CharField())


class StoreTimelineEventSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices)
    at = serializers.DateTimeField()


class StoreOptionSerializer(serializers.ModelSerializer):
    name = LocalizedField("name")

    class Meta:
        model = Option
        fields = ["id", "name", "name_ar", "name_en", "price_delta", "is_available", "is_default"]


class StoreOptionGroupSerializer(serializers.ModelSerializer):
    name = LocalizedField("name")
    options = StoreOptionSerializer(many=True, read_only=True)
    min_select = serializers.IntegerField(source="effective_min")

    class Meta:
        model = OptionGroup
        fields = [
            "id",
            "name",
            "name_ar",
            "name_en",
            "selection_type",
            "is_required",
            "min_select",
            "max_select",
            "options",
        ]


class StoreCategorySerializer(serializers.ModelSerializer):
    name = LocalizedField("name")
    image = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "name_ar", "name_en", "image", "parent", "sort_order"]

    def get_image(self, obj: Category) -> str | None:
        return _url(obj.image)


class StoreProductSerializer(serializers.ModelSerializer):
    name = LocalizedField("name")
    description = LocalizedField("description")
    images = serializers.SerializerMethodField()
    is_available = serializers.BooleanField(source="is_orderable")
    discount_percent = serializers.SerializerMethodField()
    option_groups = StoreOptionGroupSerializer(many=True, read_only=True)
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "name_ar",
            "name_en",
            "description",
            "price",
            "compare_at_price",
            "discount_percent",
            "is_available",
            "tags",
            "prep_time_min",
            "images",
            "option_groups",
        ]

    @extend_schema_field(StoreImageSerializer(many=True))
    def get_images(self, obj: Product) -> list[dict[str, Any]]:
        return [
            {
                "url": _url(i.image),
                "thumbnail": _url(i.thumbnail) or _url(i.image),
                "width": i.width,
                "height": i.height,
            }
            for i in obj.images.all()
        ]

    def get_discount_percent(self, obj: Product) -> int | None:
        if obj.compare_at_price and obj.compare_at_price > obj.price:
            return round(100 * (obj.compare_at_price - obj.price) / obj.compare_at_price)
        return None

    def get_category_name(self, obj: Product) -> str:
        from core.models import localized
        from core.serializers import current_lang

        return localized(obj.category, "name", current_lang())


class StoreProductListSerializer(StoreProductSerializer):
    has_options = serializers.SerializerMethodField()

    class Meta(StoreProductSerializer.Meta):
        fields = [f for f in StoreProductSerializer.Meta.fields if f != "option_groups"] + [
            "has_options"
        ]

    def get_has_options(self, obj: Product) -> bool:
        return bool(obj.option_groups.all())


class StoreZoneSerializer(serializers.ModelSerializer):
    name = LocalizedField("name")

    class Meta:
        model = DeliveryZone
        fields = [
            "id",
            "name",
            "name_ar",
            "name_en",
            "areas",
            "fee",
            "min_order",
            "free_delivery_threshold",
            "eta_min",
            "eta_max",
        ]


def _ai_entitled(business: Business) -> bool:
    from apps.subscriptions.services import has_feature

    return has_feature(business.id, "ai_assistant")


def _ratings(business: Business) -> dict[str, Any]:
    from apps.orders.services.reviews import rating_summary

    return rating_summary(business)


def verification_required(business: Business) -> bool:
    from apps.customers.services import verification_required as required

    return required(business)


def business_info(business: Business, branch: Branch) -> dict[str, Any]:
    from core.models import localized
    from core.serializers import current_lang

    lang = current_lang()
    cfg = business.settings
    hours = [
        {
            "weekday": h.weekday,
            "opens_at": h.opens_at.strftime("%H:%M"),
            "closes_at": h.closes_at.strftime("%H:%M"),
        }
        for h in branch.hours.all()
    ]
    return {
        "id": str(business.id),
        "slug": business.slug,
        "name": localized(business, "name", lang),
        "name_ar": business.name_ar,
        "name_en": business.name_en,
        "description": localized(business, "description", lang),
        "business_type": business.business_type,
        "logo": _url(business.logo),
        "cover": _url(business.cover),
        "phone": business.phone,
        "currency": business.currency,
        "default_language": business.default_language,
        "is_open": is_open(branch) and business.is_active,
        "is_active": business.is_active,
        "phone_verification_required": verification_required(business),
        **_ratings(business),
        "loyalty": (
            {
                "spend_per_point": cfg.loyalty_spend_per_point,
                "point_value": cfg.loyalty_point_value,
                "min_redeem": cfg.loyalty_min_redeem,
            }
            if cfg.loyalty_enabled
            else None
        ),
        "accepts_delivery": branch.accepts_delivery,
        "accepts_pickup": branch.accepts_pickup,
        "accepts_dine_in": branch.accepts_dine_in,
        "min_order_amount": cfg.min_order_amount,
        "payment_methods": cfg.payment_methods,
        "allow_order_notes": cfg.allow_order_notes,
        "customer_cancel_window_min": cfg.customer_cancel_window_min,
        "welcome_message": localized(cfg, "welcome_message", lang),
        "ai_enabled": cfg.ai_enabled and _ai_entitled(business),
        "address": branch.address,
        "hours": hours,
    }


class StoreReviewSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True)
    reply = serializers.CharField(read_only=True)


class StoreOrderSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "number",
            "status",
            "fulfilment",
            "channel",
            "currency",
            "subtotal",
            "delivery_fee",
            "discount_total",
            "points_redeemed",
            "total",
            "payment_method",
            "placed_at",
            "customer_name",
            "customer_phone",
            "zone_name_snapshot",
            "table_label",
            "address_area",
            "address_street",
            "address_landmark",
            "notes",
            "cancel_reason",
            "items",
            "can_cancel",
            "timeline",
            "can_review",
            "review",
        ]

    @extend_schema_field(StoreOrderItemSerializer(many=True))
    def get_items(self, obj: Order) -> list[dict[str, Any]]:
        from core.serializers import current_lang

        en = current_lang() == "en"
        return [
            {
                "name": (i.product_name_en if en and i.product_name_en else i.product_name_ar),
                "quantity": i.quantity,
                "unit_price": i.unit_price,
                "line_total": i.line_total,
                "note": i.note,
                "product_id": str(i.product_id) if i.product_id else None,
                "options": [
                    (o.option_name_en if en and o.option_name_en else o.option_name_ar)
                    for o in i.options.all()
                ],
            }
            for i in obj.items.all()
        ]

    def get_can_cancel(self, obj: Order) -> bool:
        from apps.orders.services.transitions import customer_can_cancel

        return customer_can_cancel(obj)

    def get_can_review(self, obj: Order) -> bool:
        from apps.orders.services.reviews import can_review

        return can_review(obj)

    @extend_schema_field(StoreReviewSerializer(allow_null=True))
    def get_review(self, obj: Order) -> dict[str, Any] | None:
        r = getattr(obj, "review", None)
        if r is None:
            return None
        return {"rating": r.rating, "comment": r.comment, "reply": r.reply}

    @extend_schema_field(StoreTimelineEventSerializer(many=True))
    def get_timeline(self, obj: Order) -> list[dict[str, Any]]:
        return [{"status": e.to_status, "at": e.created_at} for e in obj.events.all()]
