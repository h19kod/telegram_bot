"""Platform (SaaS operator) administration API and owner-side support tickets."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_filters import rest_framework as filters
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.businesses import services as biz
from apps.businesses.models import Business, BusinessStatus, TelegramBot
from apps.chatbot.models import AIMessage
from apps.notifications.models import NotificationOutbox, OutboxStatus
from apps.orders.models import Order, OrderStatus
from apps.platform_admin.audit import audit
from apps.platform_admin.models import AuditLog, SupportMessage, SupportTicket
from apps.subscriptions import services as ent
from apps.subscriptions.models import (
    EntitlementOverride,
    Feature,
    Plan,
    PlanEntitlement,
    Subscription,
    SubscriptionPayment,
)
from core.errors import DomainError, NotFoundError
from core.health import check_components
from core.permissions import IsPlatformAdmin
from core.tenancy import IsBusinessMember, TenantViewSet

# --- Businesses ---------------------------------------------------------------------------


class PlatformBusinessSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    plan = serializers.SerializerMethodField()
    subscription_status = serializers.SerializerMethodField()
    orders_count = serializers.IntegerField(read_only=True, default=0)
    has_own_bot = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            "id",
            "slug",
            "name_ar",
            "name_en",
            "business_type",
            "status",
            "suspended_reason",
            "currency",
            "owner_email",
            "plan",
            "subscription_status",
            "orders_count",
            "has_own_bot",
            "created_at",
        ]
        read_only_fields = fields

    def _sub(self, obj: Business) -> Subscription | None:
        if not hasattr(obj, "_live_sub"):
            obj._live_sub = ent.live_subscription(obj.id)  # type: ignore[attr-defined]
        return obj._live_sub  # type: ignore[attr-defined]

    def get_plan(self, obj: Business) -> str | None:
        s = self._sub(obj)
        return s.plan.code if s else None

    def get_subscription_status(self, obj: Business) -> str | None:
        s = self._sub(obj)
        return s.status if s else None

    def get_has_own_bot(self, obj: Business) -> bool:
        return TelegramBot.objects.filter(business=obj).exists()


class PlatformBusinessCreateSerializer(serializers.Serializer):
    owner_email = serializers.EmailField()
    owner_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    slug = serializers.RegexField(r"^[a-z0-9](?:[a-z0-9_]{1,48}[a-z0-9])$")
    name_ar = serializers.CharField(max_length=120)
    name_en = serializers.CharField(max_length=120, required=False, allow_blank=True)
    business_type = serializers.CharField(max_length=16, default="restaurant")
    plan = serializers.SlugRelatedField(
        slug_field="code", queryset=Plan.objects.all(), required=False
    )

    def validate_slug(self, v: str) -> str:
        if Business.objects.filter(slug=v).exists():
            raise serializers.ValidationError("already taken")
        return v


class BusinessFilter(filters.FilterSet):
    search = filters.CharFilter(method="filter_search")
    status = filters.ChoiceFilter(choices=BusinessStatus.choices)

    class Meta:
        model = Business
        fields = ["status", "business_type"]

    def filter_search(self, qs, name, value):  # type: ignore[no-untyped-def]
        return qs.filter(
            Q(slug__icontains=value)
            | Q(name_ar__icontains=value)
            | Q(name_en__icontains=value)
            | Q(owner__email__icontains=value)
        )


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class PlatformBusinessViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsPlatformAdmin]
    serializer_class = PlatformBusinessSerializer
    filterset_class = BusinessFilter
    ordering_fields = ["created_at", "name_ar", "orders_count"]
    ordering = ["-created_at"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        from django.db.models import IntegerField, OuterRef, Subquery
        from django.db.models.functions import Coalesce

        counts = (
            Order.objects.filter(business_id=OuterRef("pk"))
            .order_by()
            .values("business_id")
            .annotate(n=Count("id"))
            .values("n")
        )
        return Business.objects.select_related("owner").annotate(
            orders_count=Coalesce(Subquery(counts, output_field=IntegerField()), 0)
        )

    def create(self, request: Request) -> Response:
        """Create a business and its owner account (the owner sets a password via reset)."""
        s = PlatformBusinessCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        owner = User.objects.filter(email__iexact=d["owner_email"]).first()
        if owner is None:
            owner = User.objects.create_user(
                email=d["owner_email"], password=None, full_name=d.get("owner_name", "")
            )
            owner.set_unusable_password()
            owner.save(update_fields=["password"])
        plan = d.get("plan")
        business = biz.create_business(
            owner,
            slug=d["slug"],
            name_ar=d["name_ar"],
            name_en=d.get("name_en", ""),
            business_type=d["business_type"],
            plan_code=plan.code if plan else None,
        )
        audit(request, "platform.business_create", business, business)
        return Response(
            PlatformBusinessSerializer(self.get_queryset().get(pk=business.pk)).data, status=201
        )

    @action(detail=True, methods=["post"])
    def suspend(self, request: Request, pk: Any = None) -> Response:
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        b = biz.suspend(self.get_object(), s.validated_data["reason"])
        audit(request, "platform.business_suspend", b, b, s.validated_data)
        return Response(self.get_serializer(b).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: Any = None) -> Response:
        b = biz.activate(self.get_object())
        audit(request, "platform.business_activate", b, b)
        return Response(self.get_serializer(b).data)

    @action(detail=True, methods=["get"])
    def usage(self, request: Request, pk: Any = None) -> Response:
        b = self.get_object()
        return Response({"entitlements": ent.resolve_all(b.id), "usage": ent.usage(b.id)})

    @action(detail=True, methods=["get", "post"])
    def subscriptions(self, request: Request, pk: Any = None) -> Response:
        b = self.get_object()
        if request.method == "POST":
            plan = serializers.SlugRelatedField(
                slug_field="code", queryset=Plan.objects.all()
            ).run_validation(request.data.get("plan"))
            months = serializers.IntegerField(min_value=0, max_value=36, default=1).run_validation(
                request.data.get("months", 1)
            )
            sub = ent.start_subscription(
                b.id, plan, months=months or None, trial=bool(request.data.get("trial"))
            )
            audit(
                request,
                "platform.subscription_start",
                b,
                sub,
                {"plan": plan.code, "months": months},
            )
        subs = (
            Subscription.objects.filter(business=b).select_related("plan").order_by("-created_at")
        )
        return Response(
            SubscriptionSerializer(subs, many=True).data,
            status=201 if request.method == "POST" else 200,
        )

    @action(detail=True, methods=["get", "put"], url_path="overrides")
    def overrides(self, request: Request, pk: Any = None) -> Response:
        b = self.get_object()
        if request.method == "PUT":
            s = OverrideSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            d = s.validated_data
            _check_value(d["feature"], d.get("value"))
            EntitlementOverride.objects.update_or_create(
                business=b,
                feature=d["feature"],
                defaults={
                    "value": d.get("value"),
                    "reason": d.get("reason", ""),
                    "expires_at": d.get("expires_at"),
                    "created_by": request.user,
                },
            )
            ent.invalidate(b.id)
            audit(
                request,
                "platform.override_set",
                b,
                None,
                {"feature": d["feature"].key, "value": d.get("value")},
            )
        return Response(
            OverrideSerializer(EntitlementOverride.objects.filter(business=b), many=True).data
        )

    @action(detail=True, methods=["delete"], url_path=r"overrides/(?P<feature_key>[a-z_]+)")
    def delete_override(
        self, request: Request, pk: Any = None, feature_key: str | None = None
    ) -> Response:
        b = self.get_object()
        EntitlementOverride.objects.filter(business=b, feature_id=feature_key).delete()
        ent.invalidate(b.id)
        audit(request, "platform.override_delete", b, None, {"feature": feature_key})
        return Response(status=204)


def _check_value(feature: Feature, value: Any) -> None:
    if value is None:
        return
    if feature.value_type == "bool" and not isinstance(value, bool):
        raise DomainError("validation_error", {"value": ["boolean expected"]}, 400)
    if feature.value_type == "int" and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise DomainError("validation_error", {"value": ["non-negative integer expected"]}, 400)


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = serializers.CharField(source="plan.code")

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "current_period_start",
            "current_period_end",
            "grace_until",
            "cancel_at_period_end",
            "created_at",
        ]


class OverrideSerializer(serializers.ModelSerializer):
    feature = serializers.SlugRelatedField(slug_field="key", queryset=Feature.objects.all())
    value = serializers.JSONField(allow_null=True, required=False)

    class Meta:
        model = EntitlementOverride
        fields = ["feature", "value", "reason", "expires_at"]


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPayment
        fields = [
            "id",
            "amount",
            "currency",
            "method",
            "reference",
            "months",
            "paid_at",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class SubscriptionPaymentView(APIView):
    permission_classes = [IsPlatformAdmin]

    def post(self, request: Request, subscription_id: Any) -> Response:
        sub = Subscription.objects.filter(id=subscription_id).first()
        if sub is None:
            raise NotFoundError()
        s = PaymentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payment = s.save(business_id=sub.business_id, subscription=sub, recorded_by=request.user)
        ent.extend_subscription(sub, payment.months)
        audit(request, "platform.payment_record", sub.business, payment, s.validated_data)
        return Response(PaymentSerializer(payment).data, status=201)


# --- Plans & features ---------------------------------------------------------------------


class FeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = ["key", "value_type", "default_value", "is_metered", "reset_period", "description"]


class FeatureViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = FeatureSerializer
    queryset = Feature.objects.all().order_by("key")
    pagination_class = None
    lookup_value_regex = "[a-z_]+"


class PlanSerializer(serializers.ModelSerializer):
    entitlements = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "monthly_price",
            "currency",
            "is_public",
            "is_active",
            "is_default",
            "trial_days",
            "sort_order",
            "entitlements",
        ]
        read_only_fields = ["id", "is_default"]

    def get_entitlements(self, obj: Plan) -> dict[str, Any]:
        return {e.feature_id: e.value for e in obj.entitlements.all()}


class PlanViewSet(viewsets.ModelViewSet):
    permission_classes = [IsPlatformAdmin]
    serializer_class = PlanSerializer
    queryset = Plan.objects.prefetch_related("entitlements").order_by("sort_order")
    pagination_class = None

    def perform_destroy(self, instance: Plan) -> None:
        if instance.subscriptions.exists() or instance.is_default:
            raise DomainError("validation_error", {"plan": ["plan in use"]}, 400)
        instance.delete()

    @action(detail=True, methods=["put"])
    def entitlements(self, request: Request, pk: Any = None) -> Response:
        """Body: {"<feature_key>": value, ...}; null = unlimited."""
        plan = self.get_object()
        if not isinstance(request.data, dict):
            raise DomainError("validation_error", {"body": ["object expected"]}, 400)
        features = {f.key: f for f in Feature.objects.all()}
        for key, value in request.data.items():
            if key not in features:
                raise DomainError("validation_error", {key: ["unknown feature"]}, 400)
            _check_value(features[key], value)
            PlanEntitlement.objects.update_or_create(
                plan=plan, feature=features[key], defaults={"value": value}
            )
        for business_id in Subscription.objects.filter(plan=plan).values_list(
            "business_id", flat=True
        ):
            ent.invalidate(business_id)
        audit(request, "platform.plan_entitlements", None, plan, dict(request.data))
        return Response(PlanSerializer(self.get_queryset().get(pk=plan.pk)).data)

    @action(detail=True, methods=["post"], url_path="make-default")
    def make_default(self, request: Request, pk: Any = None) -> Response:
        plan = self.get_object()
        Plan.objects.filter(is_default=True).update(is_default=False)
        plan.is_default = True
        plan.save(update_fields=["is_default", "updated_at"])
        return Response(PlanSerializer(plan).data)


# --- Stats & health -----------------------------------------------------------------------


class PlatformStatsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request: Request) -> Response:
        now = timezone.now()
        since = now - timedelta(days=int(request.query_params.get("days", 30)))
        orders = Order.objects.filter(placed_at__gte=since)
        agg = orders.aggregate(
            n=Count("id"),
            gmv=Sum("total", filter=Q(status=OrderStatus.DELIVERED)),
            delivered=Count("id", filter=Q(status=OrderStatus.DELIVERED)),
        )
        by_currency = list(
            orders.filter(status=OrderStatus.DELIVERED)
            .values("currency")
            .annotate(gmv=Sum("total"))
        )
        return Response(
            {
                "businesses_total": Business.objects.count(),
                "businesses_active": Business.objects.filter(status=BusinessStatus.ACTIVE).count(),
                "businesses_suspended": Business.objects.filter(
                    status=BusinessStatus.SUSPENDED
                ).count(),
                "new_businesses": Business.objects.filter(created_at__gte=since).count(),
                "orders": agg["n"],
                "delivered_orders": agg["delivered"],
                "gmv_by_currency": by_currency,
                "subscriptions_by_plan": list(
                    Subscription.objects.filter(status__in=["trialing", "active", "past_due"])
                    .values("plan__code")
                    .annotate(n=Count("id"))
                ),
                "ai_messages": AIMessage.objects.filter(created_at__gte=since, role="user").count(),
                "open_support_tickets": SupportTicket.objects.filter(
                    status__in=["open", "pending"]
                ).count(),
            }
        )


class PlatformHealthView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request: Request) -> Response:
        from django.core.cache import cache

        components = check_components()
        return Response(
            {
                "components": components,
                "outbox_pending": NotificationOutbox.objects.filter(
                    status=OutboxStatus.PENDING
                ).count(),
                "outbox_failed_24h": NotificationOutbox.objects.filter(
                    status=OutboxStatus.FAILED, updated_at__gte=timezone.now() - timedelta(days=1)
                ).count(),
                "bots": list(
                    TelegramBot.objects.values(
                        "username", "webhook_status", "last_error", "is_shared_platform_bot"
                    )
                ),
                "bot_service_heartbeat": cache.get("heartbeat:bot"),
                "worker_heartbeat": cache.get("heartbeat:worker"),
            }
        )


# --- Support tickets ----------------------------------------------------------------------


class SupportMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = SupportMessage
        fields = ["id", "body", "is_from_platform", "author_name", "created_at"]
        read_only_fields = ["id", "is_from_platform", "author_name", "created_at"]

    def get_author_name(self, obj: SupportMessage) -> str:
        return (obj.author.full_name or str(obj.author)) if obj.author else ""


class SupportTicketSerializer(serializers.ModelSerializer):
    messages = SupportMessageSerializer(many=True, read_only=True)
    body = serializers.CharField(write_only=True, max_length=5000)
    business_name = serializers.CharField(source="business.name_ar", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "subject",
            "status",
            "priority",
            "business",
            "business_name",
            "body",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "business", "messages", "created_at", "updated_at"]


class BusinessSupportViewSet(TenantViewSet):
    model = SupportTicket
    serializer_class = SupportTicketSerializer
    required_permissions = {"*": ["settings.edit"]}
    http_method_names = ["get", "post"]

    def base_queryset(self):  # type: ignore[no-untyped-def]
        return SupportTicket.objects.filter(business=self.business).prefetch_related(
            "messages__author"
        )

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        body = serializer.validated_data.pop("body")
        ticket = serializer.save(business=self.business, opened_by=self.request.user)
        SupportMessage.objects.create(ticket=ticket, author=self.request.user, body=body)

    @action(detail=True, methods=["post"])
    def messages(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        ticket = self.get_object()
        s = SupportMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(ticket=ticket, author=request.user, is_from_platform=False)
        ticket.status = "open"
        ticket.save(update_fields=["status", "updated_at"])
        return Response(s.data, status=201)


class PlatformSupportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsPlatformAdmin]
    serializer_class = SupportTicketSerializer
    filterset_fields = ["status", "priority", "business"]
    http_method_names = ["get", "patch", "post"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return (
            SupportTicket.objects.select_related("business")
            .prefetch_related("messages__author")
            .order_by("-updated_at")
        )

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        ticket = self.get_object()
        for field in ("status", "priority"):
            if field in request.data:
                setattr(
                    ticket,
                    field,
                    serializers.ChoiceField(
                        choices=SupportTicket._meta.get_field(field).choices
                    ).run_validation(request.data[field]),
                )
        ticket.save()
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=["post"])
    def messages(self, request: Request, pk: Any = None) -> Response:
        ticket = self.get_object()
        s = SupportMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save(ticket=ticket, author=request.user, is_from_platform=True)
        ticket.status = "pending"
        ticket.save(update_fields=["status", "updated_at"])
        return Response(s.data, status=201)


# --- Audit --------------------------------------------------------------------------------


class AuditSerializer(serializers.ModelSerializer):
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "business",
            "action",
            "target_type",
            "target_id",
            "changes",
            "ip",
            "created_at",
        ]

    def get_actor(self, obj: AuditLog) -> str:
        return str(obj.actor) if obj.actor else "system"


class BusinessAuditView(APIView):
    permission_classes = [IsBusinessMember]
    required_permissions = {"get": ["settings.edit"]}

    def get(self, request: Request, business_id: Any) -> Response:
        qs = AuditLog.objects.filter(business=request.business).select_related("actor")[:200]
        return Response(AuditSerializer(qs, many=True).data)


class PlatformAuditView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request: Request) -> Response:
        qs = AuditLog.objects.select_related("actor")
        if request.query_params.get("business"):
            qs = qs.filter(business_id=request.query_params["business"])
        return Response(AuditSerializer(qs[:500], many=True).data)
