from django.core.management.base import BaseCommand

from core.seed import ensure_reference_data


class Command(BaseCommand):
    help = "Create/refresh governorates, permissions, features and plans (idempotent)."

    def handle(self, *args, **options):
        ensure_reference_data()
        self.stdout.write(self.style.SUCCESS("Reference data is up to date."))
