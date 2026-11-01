from django.db import migrations


def seed(apps, schema_editor):
    from apps.staff.permissions_catalog import PERMISSIONS

    Permission = apps.get_model("staff", "Permission")
    for codename, description in PERMISSIONS.items():
        Permission.objects.update_or_create(
            codename=codename, defaults={"description": description}
        )


class Migration(migrations.Migration):
    dependencies = [("staff", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
