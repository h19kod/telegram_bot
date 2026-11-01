from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import BaseModel


class TicketStatus(models.TextChoices):
    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(models.TextChoices):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class SupportTicket(BaseModel):
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="support_tickets"
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    subject = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=TicketStatus.choices, default="open")
    priority = models.CharField(max_length=10, choices=TicketPriority.choices, default="normal")

    class Meta:
        ordering = ["-created_at"]


class SupportMessage(BaseModel):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    is_from_platform = models.BooleanField(default=False)
    body = models.TextField(max_length=5000)

    class Meta:
        ordering = ["created_at"]


class AuditLog(BaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "-created_at"])]
