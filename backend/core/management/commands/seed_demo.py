"""Create a realistic demo restaurant for local development (DEBUG only, idempotent)."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.businesses.models import Business, TelegramBot
from apps.businesses.services import create_business, default_branch
from apps.categories.models import Category
from apps.delivery.models import DeliveryZone
from apps.products.models import Option, OptionGroup, Product
from core.crypto import encrypt
from core.seed import ensure_reference_data

MENU = {
    ("برغر", "Burgers"): [
        (
            "برغر دبل",
            "Double burger",
            8000,
            9500,
            "لحم بقري طازج مزدوج مع جبن شيدر وصوص خاص",
            "Double fresh beef patty, cheddar and house sauce",
            True,
        ),
        (
            "برغر دجاج كرسبي",
            "Crispy chicken burger",
            6500,
            None,
            "صدر دجاج مقرمش مع خس ومايونيز",
            "Crispy chicken breast, lettuce, mayo",
            True,
        ),
    ],
    ("شاورما", "Shawarma"): [
        (
            "شاورمة لحم",
            "Beef shawarma",
            5000,
            None,
            "صمون حجري مع لحم وطرشي وطحينة",
            "Stone-baked bread, beef, pickles, tahini",
            True,
        ),
        (
            "شاورمة دجاج",
            "Chicken shawarma",
            4000,
            None,
            "صمون حجري مع دجاج وثومية",
            "Stone-baked bread, chicken, garlic sauce",
            True,
        ),
    ],
    ("مشروبات", "Drinks"): [
        ("بيبسي", "Pepsi", 750, None, "", "", False),
        ("عصير برتقال طبيعي", "Fresh orange juice", 2500, None, "", "", False),
        ("لبن عيران", "Ayran", 1000, None, "", "", False),
    ],
}


class Command(BaseCommand):
    help = "Create the demo_shop business with menu, zones, owner and a dev bot."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bot-token", default="", help="Real BotFather token to use (else a fake one)"
        )
        parser.add_argument("--owner-email", default="owner@demo.local")
        parser.add_argument("--owner-password", default="")

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo is for development only.")
        ensure_reference_data()
        owner, _ = User.objects.get_or_create(
            email=opts["owner_email"], defaults={"full_name": "Demo Owner"}
        )
        if opts["owner_password"]:
            owner.set_password(opts["owner_password"])
            owner.save()
        b = Business.objects.filter(slug="demo_shop").first()
        if b is None:
            b = create_business(
                owner,
                slug="demo_shop",
                name_ar="مطعم الطيب",
                name_en="Al-Tayeb Restaurant",
                plan_code="pro",
                description_ar="أطيب برغر وشاورما ببغداد",
                description_en="Baghdad's tastiest burgers and shawarma",
                phone="+9647701234567",
            )
        branch = default_branch(b)
        branch.governorate_id = "BGD"
        branch.address = "بغداد - الكرادة داخل"
        branch.save()
        b.settings.min_order_amount = 3000
        b.settings.save()
        if not Category.objects.filter(business=b).exists():
            for i, ((car, cen), items) in enumerate(MENU.items()):
                cat = Category.objects.create(business=b, name_ar=car, name_en=cen, sort_order=i)
                for j, (ar, en, price, cap, dar, den, sized) in enumerate(items):
                    p = Product.objects.create(
                        business=b,
                        category=cat,
                        name_ar=ar,
                        name_en=en,
                        price=price,
                        compare_at_price=cap,
                        description_ar=dar,
                        description_en=den,
                        sort_order=j,
                        prep_time_min=15 if sized else None,
                    )
                    if sized:
                        g = OptionGroup.objects.create(
                            business=b,
                            product=p,
                            name_ar="الحجم",
                            name_en="Size",
                            is_required=True,
                            min_select=1,
                        )
                        Option.objects.create(
                            business=b, group=g, name_ar="عادي", name_en="Regular", is_default=True
                        )
                        Option.objects.create(
                            business=b, group=g, name_ar="كبير", name_en="Large", price_delta=1500
                        )
                        x = OptionGroup.objects.create(
                            business=b,
                            product=p,
                            name_ar="إضافات",
                            name_en="Extras",
                            selection_type="multiple",
                            max_select=3,
                        )
                        Option.objects.create(
                            business=b,
                            group=x,
                            name_ar="جبن إضافي",
                            name_en="Extra cheese",
                            price_delta=500,
                        )
                        Option.objects.create(
                            business=b, group=x, name_ar="بطاطا", name_en="Fries", price_delta=1000
                        )
        if not DeliveryZone.objects.filter(business=b).exists():
            for name_ar, name_en, fee in [
                ("الكرادة", "Karrada", 2000),
                ("المنصور", "Mansour", 3000),
                ("زيونة", "Zayouna", 2500),
            ]:
                DeliveryZone.objects.create(
                    business=b,
                    branch=branch,
                    name_ar=name_ar,
                    name_en=name_en,
                    governorate_id="BGD",
                    fee=fee,
                    eta_min=30,
                    eta_max=45,
                    free_delivery_threshold=50000,
                )
        token = opts["bot_token"] or "7000000099:DEVfakeTokenDEVfakeTokenDEVfakeToken12"
        bot = TelegramBot.objects.filter(business=b).first()
        if bot is None or opts["bot_token"]:
            TelegramBot.objects.filter(business=b).delete()
            TelegramBot.objects.create(
                business=b,
                bot_telegram_id=int(token.split(":")[0]),
                username="demo_shop_bot",
                token_encrypted=encrypt(token),
                webhook_secret="dev-secret-" + "x" * 30,
                webhook_status="polling",
            )
        self.stdout.write(self.style.SUCCESS(f"demo_shop ready (business id {b.id})"))
