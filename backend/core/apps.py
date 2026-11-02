from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = "core"

    def ready(self) -> None:
        from core.rls import apply_policies

        post_migrate.connect(apply_policies, sender=self, dispatch_uid="core.rls.apply_policies")
