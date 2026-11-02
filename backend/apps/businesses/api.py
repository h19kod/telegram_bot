from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses import services
from apps.businesses.models import (
    Branch,
    Business,
    BusinessSettings,
    Closure,
    Governorate,
    PaymentMethod,
    TelegramBot,
    WorkingHours,
)
from apps.platform_admin.audit import audit
from core.errors import DomainError
from core.images import validate_and_process_image
from core.phone import InvalidPhoneNumber, normalize_phone
from core.tenancy import IsBusinessMember, TenantViewSet, require


def _phone(value: str) -> str:
    if not value:
        return ""
    try:
        return normalize_phone(value, mobile_only=False)
    except InvalidPhoneNumber:
        raise serializers.ValidationError("invalid phone") from None


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = [
            "id",
            "slug",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "business_type",
            "logo",
            "cover",
            "phone",
            "whatsapp",
            "currency",
            "default_language",
            "timezone",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "logo", "cover", "status", "created_at", "currency"]

    def validate_phone(self, v: str) -> str:
        return _phone(v)

    def validate_whatsapp(self, v: str) -> str:
        return _phone(v)

    def validate_timezone(self, v: str) -> str:
        from zoneinfo import available_timezones

        if v not in available_timezones():
            raise serializers.ValidationError("unknown timezone")
        return v


class BusinessCreateSerializer(serializers.Serializer):
    slug = serializers.RegexField(r"^[a-z0-9](?:[a-z0-9_]{1,48}[a-z0-9])$")
    name_ar = serializers.CharField(max_length=120)
    name_en = serializers.CharField(max_length=120, required=False, allow_blank=True)
    business_type = serializers.ChoiceField(
        choices=[c[0] for c in Business._meta.get_field("business_type").choices],
        default="restaurant",
    )
    currency = serializers.ChoiceField(choices=["IQD", "USD"], default="IQD")

    def validate_slug(self, v: str) -> str:
        if Business.objects.filter(slug=v).exists():
            raise serializers.ValidationError("already taken")
        return v


class MyBusinessesView(APIView):
    """Owner onboarding: create a business (the creator becomes its owner)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=BusinessCreateSerializer, responses=BusinessSerializer)
    def post(self, request: Request) -> Response:
        from django.conf import settings

        s = BusinessCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        owned = Business.objects.filter(owner=request.user).count()
        if not request.user.is_platform_admin and owned >= settings.MAX_BUSINESSES_PER_OWNER:
            raise DomainError("plan_limit_exceeded", {"feature": "businesses_per_owner"})
        business = services.create_business(request.user, **s.validated_data)
        return Response(BusinessSerializer(business).data, status=201)


class BusinessView(APIView):
    permission_classes = [IsBusinessMember]

    @extend_schema(responses=BusinessSerializer)
    def get(self, request: Request, business_id: Any) -> Response:
        return Response(BusinessSerializer(request.business).data)

    @extend_schema(request=BusinessSerializer, responses=BusinessSerializer)
    def patch(self, request: Request, business_id: Any) -> Response:
        require(request, "settings.edit")
        s = BusinessSerializer(request.business, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        audit(request, "business.update", request.business, changes=s.validated_data)
        return Response(s.data)


class BusinessImageView(APIView):
    permission_classes = [IsBusinessMember]

    @extend_schema(
        parameters=[OpenApiParameter("kind", str, OpenApiParameter.PATH, enum=["logo", "cover"])],
        request={
            "multipart/form-data": inline_serializer(
                "BusinessImageUpload", {"image": serializers.ImageField()}
            )
        },
        responses=BusinessSerializer,
    )
    def post(self, request: Request, business_id: Any, kind: str) -> Response:
        require(request, "settings.edit")
        if kind not in ("logo", "cover"):
            raise DomainError("not_found", status_code=404)
        upload = request.FILES.get("image")
        processed = validate_and_process_image(upload, max_side=1600)
        setattr(request.business, kind, processed.image)
        request.business.save(update_fields=[kind, "updated_at"])
        return Response(BusinessSerializer(request.business).data)


class SettingsSerializer(serializers.ModelSerializer):
    payment_methods = serializers.ListField(
        child=serializers.ChoiceField(choices=PaymentMethod.values), allow_empty=False
    )
    notification_chat_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, max_length=10
    )

    class Meta:
        model = BusinessSettings
        fields = [
            "min_order_amount",
            "customer_cancel_window_min",
            "auto_reject_after_min",
            "allow_order_notes",
            "payment_methods",
            "ai_enabled",
            "ai_persona_note",
            "welcome_message_ar",
            "welcome_message_en",
            "notification_chat_ids",
        ]

    def validate_customer_cancel_window_min(self, v: int) -> int:
        if v > 120:
            raise serializers.ValidationError("max 120 minutes")
        return v

    def validate_auto_reject_after_min(self, v: int | None) -> int | None:
        if v is not None and not 1 <= v <= 240:
            raise serializers.ValidationError("1-240 minutes")
        return v


class SettingsView(APIView):
    permission_classes = [IsBusinessMember]

    @extend_schema(responses=SettingsSerializer)
    def get(self, request: Request, business_id: Any) -> Response:
        return Response(SettingsSerializer(request.business.settings).data)

    @extend_schema(request=SettingsSerializer, responses=SettingsSerializer)
    def patch(self, request: Request, business_id: Any) -> Response:
        require(request, "settings.edit")
        s = SettingsSerializer(request.business.settings, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        if s.validated_data.get("ai_enabled"):
            from apps.subscriptions.services import require_feature

            require_feature(request.business.id, "ai_assistant")
        s.save()
        audit(request, "settings.update", request.business, changes=s.validated_data)
        return Response(s.data)


class TelegramStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramBot
        fields = [
            "username",
            "bot_telegram_id",
            "webhook_status",
            "last_error",
            "is_active",
            "created_at",
        ]


class TelegramTokenSerializer(serializers.Serializer):
    bot_token = serializers.RegexField(r"^\d{5,15}:[A-Za-z0-9_-]{30,64}$", write_only=True)


class TelegramView(APIView):
    """The bot token is write-only: it is never returned by any endpoint."""

    permission_classes = [IsBusinessMember]

    @extend_schema(
        responses=inline_serializer(
            "TelegramOverview",
            {
                "has_own_bot": serializers.BooleanField(),
                "bot": TelegramStatusSerializer(allow_null=True),
                "shared_bot_username": serializers.CharField(allow_null=True),
                "deep_link": serializers.URLField(allow_null=True),
            },
        )
    )
    def get(self, request: Request, business_id: Any) -> Response:
        require(request, "telegram.edit")
        bot = TelegramBot.objects.filter(business=request.business).first()
        shared = services.bot_for_business(request.business.id) if bot is None else None
        return Response(
            {
                "has_own_bot": bot is not None,
                "bot": TelegramStatusSerializer(bot).data if bot else None,
                "shared_bot_username": shared.username if shared else None,
                "deep_link": (
                    f"https://t.me/{bot.username}"
                    if bot
                    else (
                        f"https://t.me/{shared.username}?start={request.business.slug}"
                        if shared
                        else None
                    )
                ),
            }
        )

    @extend_schema(request=TelegramTokenSerializer, responses=TelegramStatusSerializer)
    def put(self, request: Request, business_id: Any) -> Response:
        require(request, "telegram.edit")
        s = TelegramTokenSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        bot = services.connect_bot(request.business, s.validated_data["bot_token"])
        audit(request, "telegram.connect", request.business, changes={"bot": bot.username})
        return Response(TelegramStatusSerializer(bot).data)

    @extend_schema(responses={204: None})
    def delete(self, request: Request, business_id: Any) -> Response:
        require(request, "telegram.edit")
        services.disconnect_bot(request.business)
        audit(request, "telegram.disconnect", request.business)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TelegramTestView(APIView):
    permission_classes = [IsBusinessMember]

    @extend_schema(
        request=None,
        responses=inline_serializer("TelegramTestResult", {"sent_to": serializers.IntegerField()}),
    )
    def post(self, request: Request, business_id: Any) -> Response:
        from apps.notifications.services import staff_test_message

        require(request, "telegram.edit")
        sent = staff_test_message(request.business, request.user)
        return Response({"sent_to": sent})


class WorkingHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkingHours
        fields = ["weekday", "opens_at", "closes_at"]


class BranchSerializer(serializers.ModelSerializer):
    hours = WorkingHoursSerializer(many=True, read_only=True)
    is_open_now = serializers.SerializerMethodField()

    class Meta:
        model = Branch
        fields = [
            "id",
            "name_ar",
            "name_en",
            "governorate",
            "address",
            "latitude",
            "longitude",
            "phone",
            "is_default",
            "is_active",
            "is_temporarily_closed",
            "accepts_delivery",
            "accepts_pickup",
            "hours",
            "is_open_now",
        ]
        read_only_fields = ["id", "is_default"]

    def validate_phone(self, v: str) -> str:
        return _phone(v)

    def get_is_open_now(self, obj: Branch) -> bool:
        return services.is_open(obj)


class ClosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Closure
        fields = ["id", "starts_at", "ends_at", "reason"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["ends_at"] <= attrs["starts_at"]:
            raise serializers.ValidationError({"ends_at": "must be after starts_at"})
        return attrs


class BranchViewSet(TenantViewSet):
    model = Branch
    serializer_class = BranchSerializer
    required_permissions = {"list": [], "retrieve": [], "write": ["settings.edit"]}
    pagination_class = None

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return self.base_queryset().prefetch_related("hours").select_related("business")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        from apps.subscriptions.services import check_limit

        check_limit(self.business.id, "max_branches", self.base_queryset().count())
        serializer.save(business=self.business)

    def perform_destroy(self, instance: Branch) -> None:
        if instance.is_default:
            raise DomainError("validation_error", {"branch": ["default branch"]}, 400)
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @extend_schema(request=WorkingHoursSerializer(many=True), responses=BranchSerializer)
    @action(detail=True, methods=["put"])
    def hours(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        branch = self.get_object()
        s = WorkingHoursSerializer(data=request.data, many=True)
        s.is_valid(raise_exception=True)
        services.set_working_hours(branch, s.validated_data)
        return Response(BranchSerializer(self.get_queryset().get(pk=branch.pk)).data)

    @action(detail=True, methods=["get", "post"], url_path="closures")
    def closures(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        branch = self.get_object()
        if request.method == "POST":
            s = ClosureSerializer(data=request.data)
            s.is_valid(raise_exception=True)
            s.save(business=self.business, branch=branch)
            return Response(s.data, status=201)
        return Response(
            ClosureSerializer(branch.closures.order_by("-starts_at")[:50], many=True).data
        )

    @extend_schema(
        parameters=[OpenApiParameter("closure_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"], url_path=r"closures/(?P<closure_id>[^/.]+)")
    def delete_closure(
        self, request: Request, business_id: Any, pk: Any = None, closure_id: Any = None
    ) -> Response:
        branch = self.get_object()
        Closure.objects.filter(branch=branch, id=closure_id).delete()
        return Response(status=204)


class GovernorateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Governorate
        fields = ["code", "name_ar", "name_en"]


class GovernorateListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GovernorateSerializer
    queryset = Governorate.objects.all()
    pagination_class = None
