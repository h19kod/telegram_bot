"""Internal API used by the bot service. Thin adapters over the same domain services."""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import translation
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services import complete_link, user_for_telegram
from apps.businesses.models import Business, TelegramBot
from apps.businesses.services import default_branch
from apps.categories.models import Category
from apps.customers.models import Customer
from apps.customers.services import upsert_from_telegram
from apps.delivery.models import DeliveryZone
from apps.notifications.outbox import enqueue
from apps.orders.models import EventSource, Order, OrderStatus
from apps.orders.serializers import (
    CheckoutSerializer,
    QuoteSerializer,
    priced_cart_data,
    quote_data,
)
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import place_order, quote
from apps.orders.services.transitions import transition
from apps.products.services import search, storefront_products
from apps.staff.models import Membership
from apps.storefront.serializers import (
    StoreCategorySerializer,
    StoreOrderSerializer,
    StoreProductListSerializer,
    StoreProductSerializer,
    StoreZoneSerializer,
    business_info,
)
from apps.storefront.views import checkout_input, idempotency_key
from core.errors import DomainError, NotFoundError
from core.middleware import set_business_context

from .auth import IsService, ServiceAuthentication

PAGE_SIZE = 8


class InternalView(APIView):
    authentication_classes = [ServiceAuthentication]
    permission_classes = [IsService]
    throttle_classes: list = []

    def bot(self, bot_id: Any) -> TelegramBot:
        bot = TelegramBot.objects.filter(id=bot_id, is_active=True).first()
        if bot is None:
            raise NotFoundError()
        return bot

    def business(self, request: Request, bot: TelegramBot) -> Business:
        if bot.business_id:
            business = Business.objects.select_related("settings").get(pk=bot.business_id)
        else:
            slug = request.query_params.get("business") or request.data.get("business")
            business = (
                Business.objects.select_related("settings").filter(slug=slug).first()
                if slug
                else None
            )
            if business is None:
                raise DomainError("business_unavailable", status_code=404)
        set_business_context(business.id)
        return business

    def customer(self, business: Business, tg_id: int) -> Customer:
        c = (
            Customer.objects.select_related("business__settings")
            .filter(business=business, telegram_user_id=tg_id)
            .first()
        )
        if c is None:
            c = upsert_from_telegram(business.id, telegram_user_id=tg_id)
        translation.activate(c.language)
        return c


class BotsView(InternalView):
    def get(self, request: Request) -> Response:
        bots = TelegramBot.objects.filter(is_active=True)
        return Response(
            [
                {"id": str(b.id), "username": b.username, "is_shared": b.is_shared_platform_bot}
                for b in bots
            ]
        )


class BotCredentialsView(InternalView):
    def get(self, request: Request, bot_id: uuid.UUID) -> Response:
        bot = self.bot(bot_id)
        return Response(
            {
                "id": str(bot.id),
                "token": bot.token,
                "webhook_secret": bot.webhook_secret,
                "is_shared": bot.is_shared_platform_bot,
                "username": bot.username,
            }
        )


class TelegramUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    username = serializers.CharField(max_length=64, required=False, allow_blank=True)
    language_code = serializers.CharField(max_length=8, required=False, allow_blank=True)


class SessionView(InternalView):
    """Called on /start and whenever the bot needs fresh context for a chat."""

    def post(self, request: Request, bot_id: uuid.UUID) -> Response:
        bot = self.bot(bot_id)
        s = TelegramUserSerializer(data=request.data.get("user", {}))
        s.is_valid(raise_exception=True)
        business = self.business(request, bot)
        u = s.validated_data
        customer = upsert_from_telegram(
            business.id,
            telegram_user_id=u["id"],
            first_name=u.get("first_name", ""),
            last_name=u.get("last_name", ""),
            username=u.get("username", ""),
            language_code=u.get("language_code", ""),
        )
        translation.activate(customer.language)
        user = user_for_telegram(u["id"])
        is_staff = bool(
            user
            and Membership.objects.filter(business=business, user=user, is_active=True).exists()
        )
        return Response(
            {
                "business": business_info(business, default_branch(business)),
                "customer": {
                    "id": str(customer.id),
                    "language": customer.language,
                    "full_name": customer.full_name,
                    "phone": customer.phone,
                    "is_blocked": customer.is_blocked,
                },
                "is_staff": is_staff,
                "mini_app_url": _mini_app_url(business),
            }
        )


def _mini_app_url(business: Business) -> str | None:
    from django.conf import settings

    base = settings.MINI_APP_BASE_URL.rstrip("/")
    return f"{base}/?b={business.slug}" if base else None


class CategoriesView(InternalView):
    def get(self, request: Request, bot_id: uuid.UUID) -> Response:
        business = self.business(request, self.bot(bot_id))
        _lang(request)
        qs = Category.objects.for_business(business).filter(is_active=True, is_archived=False)
        return Response(StoreCategorySerializer(qs, many=True).data)


def _lang(request: Request) -> None:
    lang = request.query_params.get("lang")
    if lang in ("ar", "en"):
        translation.activate(lang)


class ProductsView(InternalView):
    def get(self, request: Request, bot_id: uuid.UUID) -> Response:
        business = self.business(request, self.bot(bot_id))
        _lang(request)
        qs = storefront_products(business.id)
        if request.query_params.get("category"):
            qs = qs.filter(category_id=request.query_params["category"])
        if request.query_params.get("search"):
            qs = search(qs, request.query_params["search"][:100])
        try:
            page = max(int(request.query_params.get("page", "1")), 1)
        except ValueError:
            page = 1
        total = qs.count()
        items = qs[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        return Response(
            {
                "results": StoreProductListSerializer(items, many=True).data,
                "page": page,
                "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1),
                "count": total,
            }
        )


class ProductDetailView(InternalView):
    def get(self, request: Request, bot_id: uuid.UUID, product_id: uuid.UUID) -> Response:
        business = self.business(request, self.bot(bot_id))
        _lang(request)
        p = storefront_products(business.id).filter(id=product_id).first()
        if p is None:
            raise NotFoundError()
        return Response(StoreProductSerializer(p).data)


class ZonesView(InternalView):
    def get(self, request: Request, bot_id: uuid.UUID) -> Response:
        business = self.business(request, self.bot(bot_id))
        _lang(request)
        qs = DeliveryZone.objects.for_business(business).filter(
            branch=default_branch(business), is_active=True
        )
        return Response(StoreZoneSerializer(qs, many=True).data)


class CustomerScoped(InternalView):
    def ctx(self, request: Request, bot_id: Any, tg_id: int) -> tuple[Business, Customer]:
        business = self.business(request, self.bot(bot_id))
        return business, self.customer(business, tg_id)


def _cart(customer: Customer, business: Business) -> dict[str, Any]:
    branch = default_branch(business)
    data = priced_cart_data(
        cart_svc.price_cart(cart_svc.get_active_cart(customer, branch, create=False))
    )
    data["currency"] = business.currency
    return data


class CartView(CustomerScoped):
    def get(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        return Response(_cart(customer, business))

    def delete(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        cart_svc.clear(customer, default_branch(business))
        return Response(_cart(customer, business))


class CartItemsView(CustomerScoped):
    def post(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        from apps.storefront.views import AddItemSerializer

        business, customer = self.ctx(request, bot_id, tg_id)
        s = AddItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        cart_svc.add_item(
            customer,
            default_branch(business),
            d["product_id"],
            d["option_ids"],
            d["quantity"],
            d["note"],
        )
        return Response(_cart(customer, business), status=201)


class CartItemView(CustomerScoped):
    def patch(
        self, request: Request, bot_id: uuid.UUID, tg_id: int, item_id: uuid.UUID
    ) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        qty = serializers.IntegerField(min_value=0, max_value=99).run_validation(
            request.data.get("quantity")
        )
        cart_svc.update_item_quantity(customer, item_id, qty)
        return Response(_cart(customer, business))

    def delete(
        self, request: Request, bot_id: uuid.UUID, tg_id: int, item_id: uuid.UUID
    ) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        cart_svc.remove_item(customer, item_id)
        return Response(_cart(customer, business))


class QuoteView(CustomerScoped):
    def post(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        s = QuoteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        q = quote(customer, default_branch(business), checkout_input(s.validated_data, "bot", None))
        return Response(quote_data(q))


class CheckoutView(CustomerScoped):
    def post(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        key = idempotency_key(request)
        s = CheckoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        channel = request.data.get("channel", "bot")
        channel = channel if channel in ("bot", "ai") else "bot"
        order, created = place_order(
            customer, default_branch(business), checkout_input(s.validated_data, channel, key)
        )
        order = _orders(customer).get(pk=order.pk)
        return Response(StoreOrderSerializer(order).data, status=201 if created else 200)


def _orders(customer: Customer):  # type: ignore[no-untyped-def]
    return (
        Order.objects.filter(business_id=customer.business_id, customer=customer)
        .select_related("business__settings")
        .prefetch_related("items__options", "events")
    )


class OrdersView(CustomerScoped):
    def get(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        _, customer = self.ctx(request, bot_id, tg_id)
        return Response(
            StoreOrderSerializer(_orders(customer).order_by("-placed_at")[:10], many=True).data
        )


class OrderDetailView(CustomerScoped):
    def get(self, request: Request, bot_id: uuid.UUID, tg_id: int, order_id: uuid.UUID) -> Response:
        _, customer = self.ctx(request, bot_id, tg_id)
        order = _orders(customer).filter(id=order_id).first()
        if order is None:
            raise NotFoundError()
        return Response(StoreOrderSerializer(order).data)


class OrderCancelView(CustomerScoped):
    def post(
        self, request: Request, bot_id: uuid.UUID, tg_id: int, order_id: uuid.UUID
    ) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        transition(
            business_id=business.id,
            order_id=order_id,
            to=OrderStatus.CANCELLED,
            source=EventSource.CUSTOMER,
            customer=customer,
        )
        return Response(StoreOrderSerializer(_orders(customer).get(id=order_id)).data)


class CustomerMeView(CustomerScoped):
    def patch(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        _, customer = self.ctx(request, bot_id, tg_id)
        lang = request.data.get("language")
        if lang in ("ar", "en"):
            customer.language = lang
            customer.save(update_fields=["language", "updated_at"])
        return Response({"language": customer.language})


class SupportView(CustomerScoped):
    def post(self, request: Request, bot_id: uuid.UUID, tg_id: int) -> Response:
        business, customer = self.ctx(request, bot_id, tg_id)
        text = serializers.CharField(max_length=1000, min_length=2).run_validation(
            request.data.get("message")
        )
        enqueue(
            "support.message",
            business.id,
            {"customer_id": str(customer.id), "text": text},
            dedup_key=f"support:{uuid.uuid4()}",
        )
        return Response({"sent": True}, status=201)


class StaffTransitionSerializer(serializers.Serializer):
    order_id = serializers.UUIDField()
    to = serializers.CharField(max_length=20)
    expected_version = serializers.IntegerField(min_value=1)
    telegram_user_id = serializers.IntegerField()
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True)


class StaffTransitionView(InternalView):
    """A staff member pressed an order button. Identity = linked Telegram account."""

    def post(self, request: Request, bot_id: uuid.UUID) -> Response:
        bot = self.bot(bot_id)
        s = StaffTransitionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        order = Order.objects.filter(id=d["order_id"]).only("business_id").first()
        if order is None or (bot.business_id and order.business_id != bot.business_id):
            raise NotFoundError()
        user = user_for_telegram(d["telegram_user_id"])
        membership = (
            Membership.objects.select_related("role", "user", "business")
            .filter(user=user, business_id=order.business_id, is_active=True)
            .first()
            if user
            else None
        )
        if membership is None:
            raise DomainError("permission_denied", {"reason": "not_linked"}, 403)
        result = transition(
            business_id=order.business_id,
            order_id=order.id,
            to=d["to"],
            source=EventSource.TELEGRAM,
            membership=membership,
            expected_version=d["expected_version"],
            reason=d.get("reason", ""),
        )
        return Response(
            {
                "applied": result.applied,
                "status": result.order.status,
                "version": result.order.version,
                "number": result.order.number,
            }
        )


class StaffLinkView(InternalView):
    def post(self, request: Request, bot_id: uuid.UUID) -> Response:
        self.bot(bot_id)
        s = TelegramUserSerializer(data=request.data.get("user", {}))
        s.is_valid(raise_exception=True)
        code = serializers.CharField(max_length=16).run_validation(request.data.get("code"))
        u = s.validated_data
        user = complete_link(code, u["id"], u.get("username", ""), u.get("first_name", ""))
        businesses = list(
            Membership.objects.filter(user=user, is_active=True).values_list(
                "business__name_ar", flat=True
            )
        )
        return Response(
            {"linked": True, "name": user.full_name or str(user), "businesses": businesses}
        )
