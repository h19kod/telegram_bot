from __future__ import annotations

from django.db import models

from core.models import TenantModel


class KnowledgeEntry(TenantModel):
    topic = models.CharField(max_length=200)
    answer_ar = models.TextField(max_length=2000)
    answer_en = models.TextField(max_length=2000, blank=True)
    is_active = models.BooleanField(default=True)


class ConversationStatus(models.TextChoices):
    ACTIVE = "active"
    HANDED_OVER = "handed_over"
    CLOSED = "closed"


class AIConversation(TenantModel):
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="ai_conversations"
    )
    status = models.CharField(
        max_length=12, choices=ConversationStatus.choices, default=ConversationStatus.ACTIVE
    )
    handed_over_to = models.ForeignKey(
        "staff.Membership", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    last_activity_at = models.DateTimeField(auto_now=True)


class AIMessageRole(models.TextChoices):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AIMessage(TenantModel):
    conversation = models.ForeignKey(
        AIConversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=AIMessageRole.choices)
    content = models.TextField()
    tool_name = models.CharField(max_length=64, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    provider = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["created_at"]


class ProposalStatus(models.TextChoices):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AIProposal(TenantModel):
    conversation = models.ForeignKey(
        AIConversation, on_delete=models.CASCADE, related_name="proposals"
    )
    raw_intent = models.JSONField(default=dict)
    validated_lines = models.JSONField(default=list)
    status = models.CharField(
        max_length=10, choices=ProposalStatus.choices, default=ProposalStatus.PROPOSED
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
