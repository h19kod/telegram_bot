"""Printable QR code of the shop's Telegram link."""

import pytest

from apps.businesses.models import TelegramBot
from apps.businesses.services import store_link
from core.crypto import encrypt
from tests.factories import make_business, make_member
from tests.helpers import attach_bot, auth

pytestmark = pytest.mark.django_db


def test_store_link_prefers_own_bot_then_shared_bot_with_slug():
    b = make_business()
    assert store_link(b) is None
    TelegramBot.objects.create(
        is_shared_platform_bot=True,
        bot_telegram_id=999001,
        username="platform_bot",
        token_encrypted=encrypt("1:x"),
        webhook_secret="s" * 40,
    )
    assert store_link(b) == f"https://t.me/platform_bot?start={b.slug}"
    attach_bot(b)
    assert store_link(b) == f"https://t.me/{b.slug}_bot"


def test_qr_svg_and_png(api):
    b = make_business()
    attach_bot(b)
    auth(api, b.owner)
    r = api.get(f"/api/v1/b/{b.id}/qr")
    assert r.status_code == 200
    assert r["Content-Type"] == "image/svg+xml"
    assert r.content.startswith(b"<svg")
    r = api.get(f"/api/v1/b/{b.id}/qr?type=png")
    assert r["Content-Type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_qr_needs_a_bot_and_settings_permission(api):
    b = make_business()
    auth(api, b.owner)
    assert api.get(f"/api/v1/b/{b.id}/qr").json()["error"]["code"] == "business_unavailable"
    attach_bot(b)
    auth(api, make_member(b, "Kitchen").user)
    assert api.get(f"/api/v1/b/{b.id}/qr").status_code == 403
