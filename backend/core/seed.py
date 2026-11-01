"""Idempotent reference data: governorates, permission catalog, features and plans."""

from __future__ import annotations

import importlib

from django.db import transaction


@transaction.atomic
def ensure_reference_data() -> None:
    from apps.businesses.models import Governorate
    from apps.staff.services import sync_permission_catalog
    from apps.subscriptions.catalog import FEATURES, PLANS
    from apps.subscriptions.models import Feature, Plan, PlanEntitlement

    gov = importlib.import_module("apps.businesses.migrations.0002_seed_governorates")
    for i, (code, ar, en) in enumerate(gov.GOVERNORATES):
        Governorate.objects.update_or_create(
            code=code, defaults={"name_ar": ar, "name_en": en, "sort_order": i}
        )
    sync_permission_catalog()
    features = {}
    for key, vtype, default, metered, reset, desc in FEATURES:
        features[key], _ = Feature.objects.get_or_create(
            key=key,
            defaults={
                "value_type": vtype,
                "default_value": default,
                "is_metered": metered,
                "reset_period": reset,
                "description": desc,
            },
        )
    for order, (code, cfg) in enumerate(PLANS.items()):
        plan, _ = Plan.objects.get_or_create(
            code=code,
            defaults={
                "name_ar": cfg["name_ar"],
                "name_en": cfg["name_en"],
                "monthly_price": cfg["price"],
                "is_default": cfg["default"],
                "trial_days": cfg["trial"],
                "sort_order": order,
            },
        )
        for key, feature in features.items():
            PlanEntitlement.objects.get_or_create(
                plan=plan,
                feature=feature,
                defaults={"value": cfg["values"].get(key, feature.default_value)},
            )
