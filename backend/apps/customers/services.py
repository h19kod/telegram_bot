from __future__ import annotations

from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.customers.models import Customer


def upsert_from_telegram(
    business_id: Any,
    *,
    telegram_user_id: int,
    first_name: str = "",
    last_name: str = "",
    username: str = "",
    language_code: str = "",
) -> Customer:
    defaults = {
        "first_name": first_name[:128],
        "last_name": last_name[:128],
        "telegram_username": username[:64],
        "last_seen_at": timezone.now(),
    }
    customer = Customer.objects.filter(
        business_id=business_id, telegram_user_id=telegram_user_id
    ).first()
    if customer is None:
        lang = "en" if language_code.startswith("en") else "ar"
        try:
            with transaction.atomic():
                return Customer.objects.create(
                    business_id=business_id,
                    telegram_user_id=telegram_user_id,
                    language=lang,
                    **defaults,
                )
        except IntegrityError:
            customer = Customer.objects.get(
                business_id=business_id, telegram_user_id=telegram_user_id
            )
    changed = [k for k, v in defaults.items() if v and getattr(customer, k) != v]
    for k in changed:
        setattr(customer, k, defaults[k])
    if changed:
        customer.save(update_fields=[*changed, "updated_at"])
    return customer
