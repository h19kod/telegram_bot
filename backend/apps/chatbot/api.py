from __future__ import annotations

from typing import Any

from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.chatbot.models import AIConversation, AIMessage, ConversationStatus, KnowledgeEntry
from core.tenancy import IsBusinessMember, TenantViewSet


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
    class Meta:
        model = AIMessage
        fields = ["id", "role", "content", "tool_name", "created_at", "error"]


class ConversationSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.display_name", read_only=True)
    messages = serializers.SerializerMethodField()

    class Meta:
        model = AIConversation
        fields = ["id", "customer", "customer_name", "status", "last_activity_at", "messages"]

    def get_messages(self, obj: AIConversation) -> list[dict[str, Any]]:
        if not self.context.get("detail"):
            return []
        qs = obj.messages.exclude(role="tool").order_by("created_at")[:200]
        return AIMessageSerializer(qs, many=True).data


class ConversationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsBusinessMember]
    required_permissions = {"*": ["ai.manage"]}
    serializer_class = ConversationSerializer
    filterset_fields = ["status"]
    ordering = ["-last_activity_at"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return AIConversation.objects.for_business(self.request.business).select_related("customer")

    def get_serializer_context(self) -> dict[str, Any]:
        ctx = super().get_serializer_context()
        ctx["detail"] = self.action == "retrieve"
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
