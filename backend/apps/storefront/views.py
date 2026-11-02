from __future__ import annotations

import uuid
from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.businesses.models import Business
from apps.businesses.services import bot_for_business, default_branch
from apps.categories.models import Category
from apps.customers import services as customer_svc
from apps.customers.models import AddressLabel, CustomerAddress
from apps.customers.services import upsert_from_telegram
from apps.delivery.models import DeliveryZone
from apps.notifications.outbox import enqueue
from apps.orders.models import EventSource, Order
from apps.orders.serializers import (
    CheckoutSerializer,
    QuoteSerializer,
    priced_cart_data,
    quote_data,
)
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order, quote
from apps.orders.services.transitions import transition
from apps.products.services import search, storefront_products
from apps.storefront.auth import CustomerTokenAuthentication, IsStoreCustomer, issue_customer_token
from apps.storefront.schema import (
    CancelSerializer,
    CartResponseSerializer,
    PhoneCodeConfirmSerializer,
    PhoneCodeRequestSerializer,
    PhoneCodeSentSerializer,
    ProductPageSerializer,
    QuantitySerializer,
    QuoteResponseSerializer,
    SentSerializer,
    SessionResponseSerializer,
    StoreInfoSerializer,
    StoreMeSerializer,
    StoreSupportMessageSerializer,
)
from apps.storefront.serializers import (
    StoreCategorySerializer,
    StoreOrderSerializer,
    StoreProductListSerializer,
    StoreProductSerializer,
    StoreZoneSerializer,
    business_info,
)
from core.errors import DomainError, NotFoundError
from core.models import Language
from core.phone import InvalidPhoneNumber, normalize_phone
from core.telegram import InitDataError, validate_init_data

IDEMPOTENCY = OpenApiParameter(
    "Idempotency-Key",
    OpenApiTypes.UUID,
    OpenApiParameter.HEADER,
    required=True,
    description="Client-generated UUID; retries with the same key return the same order.",
)
PRODUCT_FILTERS = [
    OpenApiParameter("category", OpenApiTypes.UUID),
    OpenApiParameter("search", str, description="Arabic-normalised search, max 100 chars"),
    OpenApiParameter("tag", str),
    OpenApiParameter("available", bool),
    OpenApiParameter("discounted", bool),
    OpenApiParameter("cursor", str),
    OpenApiParameter("page_size", int, description="Max 50"),
]


class StoreThrottle(SimpleRateThrottle):
    scope = "store"

    def get_cache_key(self, request: Request, view: Any) -> str | None:
        customer = getattr(request, "customer", None)
        ident = f"c{customer.pk}" if customer else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class CheckoutThrottle(StoreThrottle):
    scope = "checkout"


class StoreView(APIView):
    authentication_classes = [CustomerTokenAuthentication]
    permission_classes = [IsStoreCustomer]
    throttle_classes = [StoreThrottle]

    @property
    def customer(self):  # type: ignore[no-untyped-def]
        return self.request.customer

    @property
    def business(self) -> Business:
        return self.request.customer.business

    def branch(self):  # type: ignore[no-untyped-def]
        return default_branch(self.business)


class SessionSerializer(serializers.Serializer):
    init_data = serializers.CharField(max_length=4096)


@extend_schema(
    tags=["storefront"], request=SessionSerializer, responses=SessionResponseSerializer, auth=[]
)
class SessionView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [StoreThrottle]

    def post(self, request: Request, slug: str) -> Response:
        s = SessionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        business = get_object_or_404(Business, slug=slug)
        bot = bot_for_business(business.id)
        if bot is None:
            raise DomainError("business_unavailable")
        try:
            tg_user = validate_init_data(s.validated_data["init_data"], bot.token)
        except InitDataError:
            raise DomainError("invalid_init_data", status_code=401) from None
        customer = upsert_from_telegram(
            business.id,
            telegram_user_id=tg_user.id,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            username=tg_user.username,
            language_code=tg_user.language_code,
        )
        return Response(
            {
                "token": issue_customer_token(customer),
                "customer": _me(customer),
                "business": business_info(business, default_branch(business)),
            }
        )


def _me(customer) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "id": str(customer.id),
        "first_name": customer.first_name,
        "full_name": customer.full_name,
        "phone": customer.phone,
        "phone_verified": customer.phone_verified,
        "language": customer.language,
        "orders_count": customer.orders_count,
    }


@extend_schema(tags=["storefront"], responses=StoreInfoSerializer)
class InfoView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        branch = self.branch()
        return Response(business_info(self.business, branch))


@extend_schema(tags=["storefront"], responses=StoreCategorySerializer(many=True))
class CategoriesView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        qs = Category.objects.for_business(self.business).filter(is_active=True, is_archived=False)
        return Response(StoreCategorySerializer(qs, many=True).data)


class ProductPagination(CursorPagination):
    page_size = 20
    max_page_size = 50
    page_size_query_param = "page_size"
    ordering = ("sort_order", "created_at", "id")


@extend_schema_view(
    get=extend_schema(
        operation_id="store_products_list",
        parameters=PRODUCT_FILTERS,
        responses=ProductPageSerializer,
    )
)
@extend_schema(tags=["storefront"])
class ProductsView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        qs = storefront_products(self.business.id)
        p = request.query_params
        if p.get("category"):
            try:
                qs = qs.filter(category_id=uuid.UUID(p["category"]))
            except ValueError:
                raise DomainError("validation_error", {"category": ["invalid"]}, 400) from None
        if p.get("search"):
            qs = search(qs, p["search"][:100])
        if p.get("tag"):
            qs = qs.filter(tags__contains=[p["tag"][:32]])
        if p.get("available") == "true":
            qs = qs.filter(availability="available")
        if p.get("discounted") == "true":
            qs = qs.filter(compare_at_price__isnull=False)
        paginator = ProductPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(StoreProductListSerializer(page, many=True).data)


@extend_schema(tags=["storefront"], responses=StoreProductSerializer)
class ProductDetailView(StoreView):
    def get(self, request: Request, slug: str, product_id: uuid.UUID) -> Response:
        product = storefront_products(self.business.id).filter(id=product_id).first()
        if product is None:
            raise NotFoundError()
        return Response(StoreProductSerializer(product).data)


@extend_schema(tags=["storefront"], responses=StoreZoneSerializer(many=True))
class ZonesView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        qs = DeliveryZone.objects.for_business(self.business).filter(
            branch=self.branch(), is_active=True
        )
        return Response(StoreZoneSerializer(qs, many=True).data)


def cart_response(customer, branch) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    cart = cart_svc.get_active_cart(customer, branch, create=False)
    data = priced_cart_data(cart_svc.price_cart(cart))
    data["currency"] = customer.business.currency
    return data


class AddItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    option_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=30, default=list
    )
    quantity = serializers.IntegerField(min_value=1, max_value=99, default=1)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


@extend_schema(tags=["storefront"], responses=CartResponseSerializer)
class CartView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        return Response(cart_response(self.customer, self.branch()))

    def delete(self, request: Request, slug: str) -> Response:
        cart_svc.clear(self.customer, self.branch())
        return Response(cart_response(self.customer, self.branch()))


@extend_schema(
    tags=["storefront"], request=AddItemSerializer, responses={201: CartResponseSerializer}
)
class CartItemsView(StoreView):
    def post(self, request: Request, slug: str) -> Response:
        s = AddItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        cart_svc.add_item(
            self.customer, self.branch(), d["product_id"], d["option_ids"], d["quantity"], d["note"]
        )
        return Response(cart_response(self.customer, self.branch()), status=201)


@extend_schema_view(
    patch=extend_schema(request=QuantitySerializer),
)
@extend_schema(tags=["storefront"], responses=CartResponseSerializer)
class CartItemView(StoreView):
    def patch(self, request: Request, slug: str, item_id: uuid.UUID) -> Response:
        qty = serializers.IntegerField(min_value=0, max_value=99).run_validation(
            request.data.get("quantity")
        )
        cart_svc.update_item_quantity(self.customer, item_id, qty)
        return Response(cart_response(self.customer, self.branch()))

    def delete(self, request: Request, slug: str, item_id: uuid.UUID) -> Response:
        cart_svc.remove_item(self.customer, item_id)
        return Response(cart_response(self.customer, self.branch()))


def checkout_input(data: dict[str, Any], channel: str, key: uuid.UUID | None) -> CheckoutInput:
    return CheckoutInput(
        fulfilment=data["fulfilment"],
        customer_name=data["customer_name"],
        customer_phone=data["customer_phone"],
        idempotency_key=key,
        channel=channel,
        zone_id=data.get("zone_id"),
        address_area=data.get("address_area", ""),
        address_street=data.get("address_street", ""),
        address_landmark=data.get("address_landmark", ""),
        address_building=data.get("address_building", ""),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        notes=data.get("notes", ""),
        payment_method=data.get("payment_method", ""),
        coupon_code=data.get("coupon_code", ""),
    )


def idempotency_key(request: Request) -> uuid.UUID:
    raw = request.headers.get("Idempotency-Key", "")
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise DomainError("idempotency_key_required", status_code=400) from None


@extend_schema(tags=["storefront"], request=QuoteSerializer, responses=QuoteResponseSerializer)
class QuoteView(StoreView):
    def post(self, request: Request, slug: str) -> Response:
        s = QuoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        q = quote(self.customer, self.branch(), checkout_input(s.validated_data, "mini_app", None))
        return Response(quote_data(q))


@extend_schema(
    tags=["storefront"],
    request=CheckoutSerializer,
    parameters=[IDEMPOTENCY],
    responses={201: StoreOrderSerializer, 200: StoreOrderSerializer},
)
class CheckoutView(StoreView):
    throttle_classes = [StoreThrottle, CheckoutThrottle]

    def post(self, request: Request, slug: str) -> Response:
        key = idempotency_key(request)
        s = CheckoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order, created = place_order(
            self.customer, self.branch(), checkout_input(s.validated_data, "mini_app", key)
        )
        order = _orders(self.customer).get(pk=order.pk)
        return Response(
            StoreOrderSerializer(order).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _orders(customer):  # type: ignore[no-untyped-def]
    return (
        Order.objects.filter(business_id=customer.business_id, customer=customer)
        .select_related("business__settings")
        .prefetch_related("items__options", "events")
    )


@extend_schema_view(
    get=extend_schema(operation_id="store_orders_list", responses=StoreOrderSerializer(many=True))
)
@extend_schema(tags=["storefront"])
class OrdersView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        qs = _orders(self.customer).order_by("-placed_at")[:50]
        return Response(StoreOrderSerializer(qs, many=True).data)


@extend_schema(tags=["storefront"], responses=StoreOrderSerializer)
class OrderDetailView(StoreView):
    def get(self, request: Request, slug: str, order_id: uuid.UUID) -> Response:
        order = _orders(self.customer).filter(id=order_id).first()
        if order is None:
            raise NotFoundError()
        return Response(StoreOrderSerializer(order).data)


@extend_schema(tags=["storefront"], request=CancelSerializer, responses=StoreOrderSerializer)
class OrderCancelView(StoreView):
    def post(self, request: Request, slug: str, order_id: uuid.UUID) -> Response:
        transition(
            business_id=self.business.id,
            order_id=order_id,
            to="cancelled",
            source=EventSource.CUSTOMER,
            customer=self.customer,
            reason=str(request.data.get("reason", ""))[:300],
        )
        return Response(StoreOrderSerializer(_orders(self.customer).get(id=order_id)).data)


class MeSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=Language.choices, required=False)

    def validate_phone(self, v: str) -> str:
        if not v:
            return ""
        try:
            return normalize_phone(v)
        except InvalidPhoneNumber:
            raise serializers.ValidationError("invalid phone") from None


@extend_schema(tags=["storefront"], request=MeSerializer, responses=StoreMeSerializer)
class MeView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        return Response(_me(self.customer))

    def patch(self, request: Request, slug: str) -> Response:
        s = MeSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        if "phone" in data:  # a typed number is unproven: verification only via /me/phone
            customer_svc.set_unverified_phone(self.customer, data.pop("phone"))
        for k, v in data.items():
            setattr(self.customer, k, v)
        if data:
            self.customer.save(update_fields=[*data, "updated_at"])
        return Response(_me(self.customer))


class PhoneCodeThrottle(StoreThrottle):
    scope = "phone_code"


@extend_schema(
    tags=["storefront"],
    request=PhoneCodeRequestSerializer,
    responses={202: PhoneCodeSentSerializer},
)
class PhoneCodeView(StoreView):
    """Send a WhatsApp code to prove the customer owns the number."""

    throttle_classes = [PhoneCodeThrottle]

    def post(self, request: Request, slug: str) -> Response:
        s = PhoneCodeRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sent = customer_svc.request_phone_code(self.customer, s.validated_data["phone"])
        return Response(
            {"phone": sent.phone, "expires_in": sent.expires_in, "resend_in": sent.resend_in},
            status=202,
        )


@extend_schema(tags=["storefront"], request=PhoneCodeConfirmSerializer, responses=StoreMeSerializer)
class PhoneConfirmView(StoreView):
    throttle_classes = [PhoneCodeThrottle]

    def post(self, request: Request, slug: str) -> Response:
        s = PhoneCodeConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        customer = customer_svc.confirm_phone_code(self.customer, s.validated_data["code"])
        return Response(_me(customer))


class AddressSerializer(serializers.ModelSerializer):
    zone = serializers.PrimaryKeyRelatedField(
        queryset=DeliveryZone.objects.none(), allow_null=True, required=False
    )
    label = serializers.ChoiceField(choices=AddressLabel.choices, default=AddressLabel.HOME)

    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "label",
            "zone",
            "area",
            "street",
            "landmark",
            "building",
            "latitude",
            "longitude",
            "is_default",
        ]
        read_only_fields = ["id"]

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        business = self.context.get("business")
        if business is not None:
            self.fields["zone"].queryset = DeliveryZone.objects.for_business(business)


@extend_schema_view(post=extend_schema(responses={201: AddressSerializer}))
@extend_schema(
    tags=["storefront"], request=AddressSerializer, responses=AddressSerializer(many=True)
)
class AddressesView(StoreView):
    def get(self, request: Request, slug: str) -> Response:
        qs = self.customer.addresses.all().order_by("-is_default", "-created_at")
        return Response(AddressSerializer(qs, many=True).data)

    def post(self, request: Request, slug: str) -> Response:
        if self.customer.addresses.count() >= 10:
            raise DomainError("validation_error", {"addresses": ["max 10"]}, 400)
        s = AddressSerializer(data=request.data, context={"business": self.business})
        s.is_valid(raise_exception=True)
        if s.validated_data.get("is_default"):
            self.customer.addresses.update(is_default=False)
        s.save(business=self.business, customer=self.customer)
        return Response(s.data, status=201)


@extend_schema_view(delete=extend_schema(responses={204: None}))
@extend_schema(tags=["storefront"], request=AddressSerializer, responses=AddressSerializer)
class AddressDetailView(StoreView):
    def _get(self, address_id: uuid.UUID) -> CustomerAddress:
        a = self.customer.addresses.filter(id=address_id).first()
        if a is None:
            raise NotFoundError()
        return a

    def patch(self, request: Request, slug: str, address_id: uuid.UUID) -> Response:
        a = self._get(address_id)
        s = AddressSerializer(
            a, data=request.data, partial=True, context={"business": self.business}
        )
        s.is_valid(raise_exception=True)
        if s.validated_data.get("is_default"):
            self.customer.addresses.exclude(pk=a.pk).update(is_default=False)
        s.save()
        return Response(s.data)

    def delete(self, request: Request, slug: str, address_id: uuid.UUID) -> Response:
        self._get(address_id).delete()
        return Response(status=204)


@extend_schema(
    tags=["storefront"], request=StoreSupportMessageSerializer, responses={201: SentSerializer}
)
class SupportView(StoreView):
    def post(self, request: Request, slug: str) -> Response:
        text = serializers.CharField(max_length=1000, min_length=2).run_validation(
            request.data.get("message")
        )
        enqueue(
            "support.message",
            self.business.id,
            {"customer_id": str(self.customer.id), "text": text},
            dedup_key=f"support:{uuid.uuid4()}",
        )
        return Response({"sent": True}, status=201)
