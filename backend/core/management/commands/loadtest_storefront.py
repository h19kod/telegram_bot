"""Simulate Mini App customers end to end against a running server (DEBUG only).

Each virtual customer: session (signed initData) → shop info → list products → product
detail → add to cart (enough to reach the minimum order) → quote → checkout. Reports p50/p95/p99 per step and the error rate.
"""

import asyncio
import json
import random
import statistics
import time
import uuid
from collections import defaultdict

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.businesses.models import Business
from apps.businesses.services import bot_for_business
from core.telegram import sign_init_data


class Command(BaseCommand):
    help = "Load-test the storefront API with N concurrent simulated customers."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://127.0.0.1:8000")
        parser.add_argument("--slug", default="demo_shop")
        parser.add_argument("--customers", type=int, default=100)
        parser.add_argument("--concurrency", type=int, default=20)

    def handle(self, *args, **o):
        if not settings.DEBUG:
            raise CommandError("loadtest_storefront is for development/staging only.")
        business = Business.objects.filter(slug=o["slug"]).first()
        bot = bot_for_business(business.id) if business else None
        if bot is None:
            raise CommandError("Unknown business or no bot")
        token = bot.token
        base = f"{o['base_url'].rstrip('/')}/api/v1/store/{o['slug']}"
        timings: dict[str, list[float]] = defaultdict(list)
        errors: dict[str, int] = defaultdict(int)
        sem = asyncio.Semaphore(o["concurrency"])

        async def step(client, name, method, url, **kw):
            t0 = time.perf_counter()
            r = await client.request(method, url, **kw)
            timings[name].append((time.perf_counter() - t0) * 1000)
            if r.status_code >= 400:
                try:
                    code = r.json()["error"]["code"]
                except (ValueError, KeyError, TypeError):
                    code = ""
                errors[f"{name} {r.status_code} {code}".strip()] += 1
                raise RuntimeError(name)
            return r.json()

        async def customer(i, client):
            async with sem:
                uid = 9_000_000 + random.randint(0, 10**8)
                init = sign_init_data(
                    {
                        "auth_date": str(int(time.time())),
                        "query_id": "lt",
                        "user": json.dumps({"id": uid, "first_name": f"LT{i}"}),
                    },
                    token,
                )
                try:
                    s = await step(
                        client, "session", "POST", f"{base}/session", json={"init_data": init}
                    )
                    h = {"Authorization": f"Customer {s['token']}"}
                    info = await step(client, "info", "GET", f"{base}/", headers=h)
                    page = await step(client, "products", "GET", f"{base}/products", headers=h)
                    simple = [p for p in page["results"] if p["is_available"]]
                    p = random.choice(simple)
                    d = await step(
                        client, "product", "GET", f"{base}/products/{p['id']}", headers=h
                    )
                    opts = [g["options"][0]["id"] for g in d["option_groups"] if g["min_select"]]
                    unit = d["price"] + sum(
                        g["options"][0]["price_delta"]
                        for g in d["option_groups"]
                        if g["min_select"]
                    )
                    qty = max(2, -(-info["min_order_amount"] // max(unit, 1)))
                    await step(
                        client,
                        "add_to_cart",
                        "POST",
                        f"{base}/cart/items",
                        headers=h,
                        json={"product_id": p["id"], "option_ids": opts, "quantity": qty},
                    )
                    body = {
                        "fulfilment": "pickup",
                        "customer_name": "Load Test",
                        "customer_phone": "07701234567",
                    }
                    await step(
                        client, "quote", "POST", f"{base}/checkout/quote", headers=h, json=body
                    )
                    await step(
                        client,
                        "checkout",
                        "POST",
                        f"{base}/checkout",
                        headers={**h, "Idempotency-Key": str(uuid.uuid4())},
                        json=body,
                    )
                except RuntimeError:
                    pass

        async def run():
            limits = httpx.Limits(max_connections=o["concurrency"] * 2)
            async with httpx.AsyncClient(timeout=30, limits=limits) as client:
                t0 = time.perf_counter()
                await asyncio.gather(*(customer(i, client) for i in range(o["customers"])))
                return time.perf_counter() - t0

        wall = asyncio.run(run())
        total = sum(len(v) for v in timings.values())
        self.stdout.write(
            f"{o['customers']} customers, concurrency {o['concurrency']}, "
            f"{total} requests in {wall:.1f}s ({total / wall:.0f} req/s)"
        )
        for name, vals in timings.items():
            vals.sort()

            def pct(p: float, vals: list[float] = vals) -> float:
                return vals[min(len(vals) - 1, int(p * len(vals)))]

            self.stdout.write(
                f"  {name:12s} n={len(vals):4d}  p50={statistics.median(vals):6.0f}ms"
                f"  p95={pct(0.95):6.0f}ms  p99={pct(0.99):6.0f}ms"
            )
        self.stdout.write(f"errors: {dict(errors) or 'none'}")
