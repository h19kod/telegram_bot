"""Entrypoint. BOT_MODE=polling (development) or webhook (production)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
from aiogram.types import Update
from aiohttp import web
from redis.asyncio import Redis

from sopbot.api import ApiError, BackendClient
from sopbot.app import build_dispatcher
from sopbot.config import settings
from sopbot.registry import BotRegistry

logger = logging.getLogger("sopbot")
MAX_CONCURRENT_UPDATES = 200
_tasks: set[asyncio.Task] = set()


def spawn(coro) -> None:  # type: ignore[no-untyped-def]
    """Fire-and-forget with a strong reference so the task is not garbage-collected."""
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def heartbeat(cache: Redis) -> None:
    # Same key format as django-redis (prefix "sop", version 1) so the backend can read it.
    while True:
        with contextlib.suppress(Exception):
            await cache.set("sop:1:heartbeat:bot", int(time.time()), ex=120)
        await asyncio.sleep(30)


# --- polling (development) ---------------------------------------------------------------


async def poll_bot(bot: Bot, dp: Dispatcher, stop: asyncio.Event) -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    offset = None
    logger.info("Polling @%s", (await bot.me()).username)
    while not stop.is_set():
        try:
            updates = await bot.get_updates(
                offset=offset,
                timeout=25,
                allowed_updates=["message", "callback_query", "my_chat_member"],
            )
        except TelegramUnauthorizedError:
            logger.error("Bot token revoked; stopping polling for bot %s", bot.id)
            return
        except (TimeoutError, TelegramNetworkError):
            await asyncio.sleep(2)
            continue
        for upd in updates:
            offset = upd.update_id + 1
            spawn(dp.feed_update(bot, upd))


async def run_polling(
    dp: Dispatcher, api: BackendClient, registry: BotRegistry, stop: asyncio.Event
) -> None:
    tasks: dict[str, asyncio.Task] = {}
    while not stop.is_set():
        try:
            active = {b["id"] for b in await api.bots()}
        except ApiError:
            logger.warning("Backend unavailable; retrying")
            active = set(tasks)
        for bot_id in active - set(tasks):
            entry = await registry.get(bot_id)
            if entry:
                tasks[bot_id] = asyncio.create_task(poll_bot(entry[0], dp, stop))
        for bot_id in set(tasks) - active:
            tasks.pop(bot_id).cancel()
            await registry.remove(bot_id)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.bots_refresh_seconds)
    for task in tasks.values():
        task.cancel()


# --- webhook (production) ----------------------------------------------------------------


def webhook_app(dp: Dispatcher, registry: BotRegistry) -> web.Application:
    sem = asyncio.Semaphore(MAX_CONCURRENT_UPDATES)

    async def handle(request: web.Request) -> web.Response:
        entry = await registry.get(request.match_info["bot_id"])
        if entry is None:
            return web.Response(status=404)
        bot, info = entry
        if not registry.verify_secret(info, request.headers.get("X-Telegram-Bot-Api-Secret-Token")):
            return web.Response(status=401)
        try:
            update = Update.model_validate(await request.json(), context={"bot": bot})
        except ValueError:
            return web.Response(status=400)

        async def process() -> None:
            async with sem:
                await dp.feed_update(bot, update)

        spawn(process())
        return web.Response(text="ok")

    async def health(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app = web.Application(client_max_size=1024 * 1024)
    app.router.add_post(r"/tg/webhook/{bot_id:[0-9a-f-]{36}}", handle)
    app.router.add_get("/healthz", health)
    return app


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, send_default_pii=False)
    redis = Redis.from_url(settings.redis_url)
    cache = Redis.from_url(settings.cache_redis_url)
    api = BackendClient()
    registry = BotRegistry(api)
    dp = build_dispatcher(redis, api, registry)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    hb = asyncio.create_task(heartbeat(cache))
    try:
        if settings.mode == "webhook":
            runner = web.AppRunner(webhook_app(dp, registry))
            await runner.setup()
            await web.TCPSite(runner, settings.webhook_host, settings.webhook_port).start()
            logger.info("Webhook server on %s:%s", settings.webhook_host, settings.webhook_port)
            await stop.wait()
            await runner.cleanup()
        else:
            await run_polling(dp, api, registry, stop)
    finally:
        hb.cancel()
        await registry.close()
        await api.close()
        await redis.aclose()
        await cache.aclose()


if __name__ == "__main__":
    asyncio.run(main())
