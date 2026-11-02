from django.db import migrations

NEW = {"reviews.reply": ("Reply to customer reviews", ["Owner", "Manager"])}


def grant(apps, schema_editor):
    """New catalog permissions also reach existing businesses' system roles."""
    Permission = apps.get_model("staff", "Permission")
    Role = apps.get_model("staff", "Role")
    for codename, (description, roles) in NEW.items():
        perm, _ = Permission.objects.update_or_create(
            codename=codename, defaults={"description": description}
        )
        for role in Role.objects.filter(is_system=True, name__in=roles):
            role.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [("staff", "0002_seed_permissions")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
