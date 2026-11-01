from __future__ import annotations

from django.db import models

from core.models import BaseModel


class OutboxStatus(models.TextChoices):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class NotificationOutbox(BaseModel):
    """Transactional outbox: written in the same transaction as the domain change."""

    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, null=True, related_name="+"
    )
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    dedup_key = models.CharField(max_length=200, unique=True)
    status = models.CharField(
        max_length=10, choices=OutboxStatus.choices, default=OutboxStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    last_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
