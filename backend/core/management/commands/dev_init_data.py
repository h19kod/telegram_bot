"""Print signed Telegram initData for browser development of the Mini App (DEBUG only)."""

import json
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.businesses.models import Business
from apps.businesses.services import bot_for_business
from core.telegram import sign_init_data


class Command(BaseCommand):
    help = "Print VITE_DEV_INIT_DATA for a business (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True)
        parser.add_argument("--user-id", type=int, default=777000)
        parser.add_argument("--first-name", default="Dev")
        parser.add_argument("--lang", default="ar", choices=["ar", "en"])

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("Refusing to sign initData outside DEBUG.")
        business = Business.objects.filter(slug=opts["slug"]).first()
        if business is None:
            raise CommandError("Unknown business slug")
        bot = bot_for_business(business.id)
        if bot is None:
            raise CommandError("Business has no bot (connect one or configure the shared bot)")
        user = {
            "id": opts["user_id"],
            "first_name": opts["first_name"],
            "language_code": opts["lang"],
        }
        fields = {
            "auth_date": str(int(time.time())),
            "query_id": "dev",
            "user": json.dumps(user, separators=(",", ":")),
        }
        self.stdout.write(sign_init_data(fields, bot.token))
