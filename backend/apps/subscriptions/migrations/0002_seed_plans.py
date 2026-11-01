from django.db import migrations


def seed(apps, schema_editor):
    from apps.subscriptions.catalog import FEATURES, PLANS

    Feature = apps.get_model("subscriptions", "Feature")
    Plan = apps.get_model("subscriptions", "Plan")
    PlanEntitlement = apps.get_model("subscriptions", "PlanEntitlement")
    features = {}
    for key, vtype, default, metered, reset, desc in FEATURES:
        features[key], _ = Feature.objects.update_or_create(
            key=key,
            defaults={"value_type": vtype, "default_value": default, "is_metered": metered,
                      "reset_period": reset, "description": desc},
        )
    for order, (code, cfg) in enumerate(PLANS.items()):
        plan, created = Plan.objects.get_or_create(
            code=code,
            defaults={"name_ar": cfg["name_ar"], "name_en": cfg["name_en"],
                      "monthly_price": cfg["price"], "is_default": cfg["default"],
                      "trial_days": cfg["trial"], "sort_order": order},
        )
        if not created:
            continue
        for key, feature in features.items():
            value = cfg["values"].get(key, feature.default_value)
            PlanEntitlement.objects.create(plan=plan, feature=feature, value=value)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
