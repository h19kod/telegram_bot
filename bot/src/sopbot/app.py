from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from sopbot.api import BackendClient
from sopbot.config import settings
from sopbot.context import UserPrefs
from sopbot.handlers import ai, cart, catalog, checkout, menu, orders, staff, start, support
from sopbot.middlewares import ContextMiddleware, ErrorMiddleware, ThrottleMiddleware
from sopbot.registry import BotRegistry


def build_dispatcher(redis: Redis, api: BackendClient, registry: BotRegistry) -> Dispatcher:
    storage = RedisStorage(redis, key_builder=DefaultKeyBuilder(with_bot_id=True))
    dp = Dispatcher(storage=storage)
    prefs = UserPrefs(redis)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(ContextMiddleware(registry, api, prefs))
        observer.outer_middleware(ThrottleMiddleware(redis, settings.throttle_seconds))
        observer.middleware(ErrorMiddleware())
    # Order matters: explicit commands & stateful flows before the free-text fallback.
    routers = [
        staff.router,
        start.router,
        checkout.router,
        support.router,
        catalog.router,
        cart.router,
        orders.router,
        ai.router,
        menu.router,
    ]
    for r in routers:  # allow rebuilding (tests, reload): routers are module-level singletons
        r._parent_router = None
    dp.include_routers(*routers)
    return dp
