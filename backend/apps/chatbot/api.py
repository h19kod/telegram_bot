from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chatbot import services
from apps.chatbot.models import AIConversation, AIMessage, ConversationStatus, KnowledgeEntry
from apps.platform_admin.audit import audit
from core.tenancy import IsBusinessMember, TenantViewSet, require


class KnowledgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeEntry
        fields = ["id", "topic", "answer_ar", "answer_en", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class KnowledgeViewSet(TenantViewSet):
    model = KnowledgeEntry
    serializer_class = KnowledgeSerializer
    required_permissions = {"*": ["ai.manage"]}
    pagination_class = None

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        if self.base_queryset().count() >= 100:
            from core.errors import DomainError

            raise DomainError("plan_limit_exceeded", {"feature": "knowledge_entries"})
        serializer.save(business=self.business)


class AIMessageSerializer(serializers.ModelSerializer):
    from_staff = serializers.SerializerMethodField()

    class Meta:
        model = AIMessage
        fields = ["id", "role", "content", "tool_name", "from_staff", "created_at", "error"]

    def get_from_staff(self, obj: AIMessage) -> bool:
        return obj.provider == "staff"


class ConversationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.display_name", read_only=True)
    messages = serializers.SerializerMethodField()

    class Meta:
        model = AIConversation
        fields = ["id", "customer", "customer_name", "status", "last_activity_at", "messages"]

    @extend_schema_field(AIMessageSerializer(many=True))
    def get_messages(self, obj: AIConversation) -> list[dict[str, Any]]:
        if not self.context.get("detail"):
            return []
        qs = obj.messages.exclude(role="tool").order_by("created_at")[:200]
        return AIMessageSerializer(qs, many=True).data


class StaffReplySerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)


class ConversationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsBusinessMember]
    required_permissions = {"*": ["ai.manage"]}
    serializer_class = ConversationSerializer
    filterset_fields = ["status"]
    ordering = ["-last_activity_at"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return (
            AIConversation.objects.for_business(getattr(self.request, "business", None))
            .filter(customer__is_sandbox=False)
            .select_related("customer")
        )

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        ctx["detail"] = self.action != "list"
        return ctx

    @action(detail=True, methods=["post"])
    def handover(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        conv = self.get_object()
        conv.status = ConversationStatus.HANDED_OVER
        conv.handed_over_to = request.membership
        conv.save(update_fields=["status", "handed_over_to", "last_activity_at"])
        return Response(self.get_serializer(conv).data)

    @action(detail=True, methods=["post"])
    def release(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        conv = self.get_object()
        conv.status = ConversationStatus.ACTIVE
        conv.handed_over_to = None
        conv.save(update_fields=["status", "handed_over_to", "last_activity_at"])
        return Response(self.get_serializer(conv).data)

    @extend_schema(request=StaffReplySerializer, responses=ConversationSerializer)
    @action(detail=True, methods=["post"])
    def reply(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        conv = self.get_object()
        s = StaffReplySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.staff_reply(conv, request.membership, s.validated_data["text"])
        audit(request, "ai.staff_reply", request.business, conv)
        return Response(self.get_serializer(conv).data)

    @action(detail=True, methods=["post"])
    def close(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        conv = services.close_conversation(self.get_object())
        return Response(self.get_serializer(conv).data)


class AIStatusSerializer(serializers.Serializer):
    configured = serializers.BooleanField(help_text="A provider key is set on the platform")
    provider = serializers.CharField()
    model = serializers.CharField()
    entitled = serializers.BooleanField(help_text="The plan includes the AI assistant")
    enabled = serializers.BooleanField(help_text="Switched on for customers")
    messages_used = serializers.IntegerField(help_text="This month")
    messages_limit = serializers.IntegerField(allow_null=True)
    handed_over = serializers.IntegerField(help_text="Conversations waiting for staff")


class PlaygroundSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=1000, allow_blank=True)
    reset = serializers.BooleanField(default=False)


class PlaygroundReplySerializer(serializers.Serializer):
    reply = serializers.CharField()
    handed_over = serializers.BooleanField()
    proposal_id = serializers.UUIDField(allow_null=True)


class AIStatusView(APIView):
    permission_classes = [IsBusinessMember]

    @extend_schema(responses=AIStatusSerializer)
    def get(self, request: Request, business_id: Any) -> Response:
        require(request, "ai.manage")
        return Response(services.ai_status(request.business))


class PlaygroundView(APIView):
    """Staff test chat with the assistant (own sandbox customer, never notifies anyone)."""

    permission_classes = [IsBusinessMember]

    @extend_schema(request=PlaygroundSerializer, responses=PlaygroundReplySerializer)
    def post(self, request: Request, business_id: Any) -> Response:
        require(request, "ai.manage")
        s = PlaygroundSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(
            services.playground_message(
                request.business,
                request.membership,
                s.validated_data["text"],
                s.validated_data["reset"],
            )
        )
