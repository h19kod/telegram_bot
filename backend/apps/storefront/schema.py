"""OpenAPI shapes of the storefront responses that are built as dicts (documentation only).

tests/test_openapi.py checks real responses against these, so they cannot drift silently.
"""

from rest_framework import serializers

from apps.businesses.models import BusinessType
from apps.storefront.serializers import StoreProductListSerializer
from core.models import Language


class StoreMeSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    first_name = serializers.CharField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    phone_verified = serializers.BooleanField()
    language = serializers.ChoiceField(choices=Language.choices)
    orders_count = serializers.IntegerField()


class PhoneCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)


class PhoneCodeSentSerializer(serializers.Serializer):
    phone = serializers.CharField(help_text="E.164 number the code was sent to")
    expires_in = serializers.IntegerField(help_text="Seconds")
    resend_in = serializers.IntegerField(help_text="Seconds before another code may be requested")


class PhoneCodeConfirmSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=12)


class OpeningHoursSerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    opens_at = serializers.CharField(help_text="HH:MM")
    closes_at = serializers.CharField(help_text="HH:MM")


class StoreInfoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    name_ar = serializers.CharField()
    name_en = serializers.CharField()
    description = serializers.CharField()
    business_type = serializers.ChoiceField(choices=BusinessType.choices)
    logo = serializers.URLField(allow_null=True)
    cover = serializers.URLField(allow_null=True)
    phone = serializers.CharField()
    currency = serializers.CharField()
    default_language = serializers.ChoiceField(choices=Language.choices)
    is_open = serializers.BooleanField()
    is_active = serializers.BooleanField()
    phone_verification_required = serializers.BooleanField()
    rating_avg = serializers.FloatField(allow_null=True, help_text="1.0-5.0, null without reviews")
    rating_count = serializers.IntegerField()
    accepts_delivery = serializers.BooleanField()
    accepts_pickup = serializers.BooleanField()
    min_order_amount = serializers.IntegerField(help_text="Minor units")
    payment_methods = serializers.ListField(child=serializers.CharField())
    allow_order_notes = serializers.BooleanField()
    customer_cancel_window_min = serializers.IntegerField()
    welcome_message = serializers.CharField()
    ai_enabled = serializers.BooleanField()
    address = serializers.CharField()
    hours = OpeningHoursSerializer(many=True)


class SessionResponseSerializer(serializers.Serializer):
    token = serializers.CharField(help_text="Send as `Authorization: Customer <token>`")
    customer = StoreMeSerializer()
    business = StoreInfoSerializer()


class CartLineOptionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    price_delta = serializers.IntegerField()


class CartLineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    name = serializers.CharField()
    image = serializers.URLField(allow_null=True)
    options = CartLineOptionSerializer(many=True)
    quantity = serializers.IntegerField()
    note = serializers.CharField()
    unit_price = serializers.IntegerField()
    line_total = serializers.IntegerField()
    available = serializers.BooleanField()
    warning = serializers.CharField()


class CartResponseSerializer(serializers.Serializer):
    lines = CartLineSerializer(many=True)
    subtotal = serializers.IntegerField()
    item_count = serializers.IntegerField()
    has_problems = serializers.BooleanField()
    currency = serializers.CharField(allow_null=True)


class QuoteCouponSerializer(serializers.Serializer):
    code = serializers.CharField()
    discount = serializers.IntegerField()


class QuoteZoneSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name_ar = serializers.CharField()
    name_en = serializers.CharField()
    eta_min = serializers.IntegerField(allow_null=True)
    eta_max = serializers.IntegerField(allow_null=True)


class QuoteResponseSerializer(serializers.Serializer):
    subtotal = serializers.IntegerField()
    delivery_fee = serializers.IntegerField()
    discount_total = serializers.IntegerField()
    total = serializers.IntegerField()
    currency = serializers.CharField()
    payment_method = serializers.CharField()
    coupon = QuoteCouponSerializer(allow_null=True)
    zone = QuoteZoneSerializer(allow_null=True)


class ProductPageSerializer(serializers.Serializer):
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = StoreProductListSerializer(many=True)


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0, max_value=99, help_text="0 removes the line")


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True)


class StoreSupportMessageSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=2, max_length=1000)


class SentSerializer(serializers.Serializer):
    sent = serializers.BooleanField()
