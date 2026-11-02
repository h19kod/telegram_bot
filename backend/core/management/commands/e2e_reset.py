"""Reset the end-to-end test database and seed it; prints JSON for Playwright (DEBUG only).

Refuses to run unless the configured database name ends in ``_e2e``: it wipes every table.
Creates that database on first use. Output: {"slug", "owner_email", "init_data"}.
"""

import json

import psycopg
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Recreate and seed the *_e2e database (Playwright end-to-end tests)."

    def add_arguments(self, parser):
        parser.add_argument("--owner-password", required=True)
        parser.add_argument("--customer-id", type=int, default=880001)

    def handle(self, *args, **opts):
        db = settings.DATABASES["default"]
        if not settings.DEBUG or not db["NAME"].endswith("_e2e"):
            raise CommandError("e2e_reset only runs with DEBUG and a database named *_e2e.")
        self._ensure_database(db)
        call_command("migrate", verbosity=0, interactive=False)
        call_command("flush", verbosity=0, interactive=False)
        call_command(
            "seed_demo", owner_password=opts["owner_password"], verbosity=0, stdout=_Null()
        )
        User.objects.filter(email="owner@demo.local").update(language="en")
        out = _Capture()
        call_command(
            "dev_init_data",
            slug="demo_shop",
            user_id=opts["customer_id"],
            first_name="E2E",
            lang="en",
            stdout=out,
        )
        connection.close()
        self.stdout.write(
            json.dumps(
                {
                    "slug": "demo_shop",
                    "owner_email": "owner@demo.local",
                    "init_data": out.value.strip(),
                }
            )
        )

    @staticmethod
    def _ensure_database(db: dict) -> None:
        params = {
            "host": db.get("HOST") or "localhost",
            "port": db.get("PORT") or 5432,
            "user": db["USER"],
            "password": db["PASSWORD"],
            "dbname": "postgres",
            "autocommit": True,
        }
        with psycopg.connect(**params) as conn:
            exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db["NAME"]])
            if exists.fetchone() is None:
                conn.execute(f'CREATE DATABASE "{db["NAME"]}"')


class _Capture:
    def __init__(self) -> None:
        self.value = ""

    def write(self, s: str) -> None:
        self.value += s

    def flush(self) -> None:
        pass


class _Null(_Capture):
    pass
