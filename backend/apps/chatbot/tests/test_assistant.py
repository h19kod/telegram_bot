import json
from types import SimpleNamespace

import pytest

from apps.chatbot.models import AIMessage, AIProposal
from apps.chatbot.providers import ScriptedProvider
from apps.chatbot.services import confirm_proposal, handle_message, mask_pii
from apps.orders.models import Cart
from apps.subscriptions.models import PlanEntitlement
from apps.subscriptions.services import invalidate
from core.errors import DomainError
from tests.factories import (
    make_business,
    make_customer,
    make_option,
    make_option_group,
    make_product,
    plan,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop(settings):
    settings.AI_PROVIDER = "scripted"
    b = make_business(plan="pro")
    b.settings.ai_enabled = True
    b.settings.save()
    burger = make_product(b, name_ar="برغر دبل", name_en="Double burger", price=8000)
    size = make_option_group(burger, name_ar="الحجم", is_required=True, min_select=1)
    large = make_option(size, name_ar="كبير", price_delta=1500)
    pepsi = make_product(b, name_ar="بيبسي", name_en="Pepsi", price=750)
    return b, make_customer(b), burger, large, pepsi


def script(*steps):
    ScriptedProvider.script = list(steps)


def test_order_from_iraqi_dialect_uses_db_prices(shop):
    b, c, burger, large, pepsi = shop
    script(
        {"tool": "search_catalog", "input": {"query": "برغر"}, "expect_error": False},
        {
            "tool": "propose_order",
            "input": {
                "items": [
                    {
                        "product_id": str(burger.id),
                        "quantity": 1,
                        "option_ids": [str(large.id)],
                        "note": "",
                    },
                    {"product_id": str(pepsi.id), "quantity": 2, "option_ids": [], "note": ""},
                ]
            },
            "expect_error": False,
        },
        {"reply": "أكيد! جهزتلك الطلب، كلشي بـ 1 دينار بس 😉"},  # a lying model
    )
    res = handle_message(b, c, "أريد برغر دبل كبير وبيبسي ثنين وخلّي التوصيل للبيت")
    assert res["proposal_id"]
    # The authoritative summary is appended by the server from DB prices.
    assert "9,500 د.ع" in res["reply"]
    assert "1,500 د.ع" in res["reply"]  # 2 × 750
    assert "11,000 د.ع" in res["reply"]
    proposal = AIProposal.objects.get(id=res["proposal_id"])
    assert sum(ln["line_total"] for ln in proposal.validated_lines) == 11000

    out = confirm_proposal(b, c, res["proposal_id"])
    assert out["added"] == 2
    cart = Cart.objects.get(customer=c, status="active")
    assert cart.items.count() == 2
    assert confirm_proposal(b, c, res["proposal_id"])["already_confirmed"]


def test_invented_product_and_missing_required_option_rejected(shop):
    b, c, burger, *_ = shop
    script(
        {
            "tool": "propose_order",
            "input": {
                "items": [
                    {
                        "product_id": "00000000-0000-0000-0000-000000000000",
                        "quantity": 1,
                        "option_ids": [],
                        "note": "",
                    }
                ]
            },
            "expect_error": True,
        },
        {
            "tool": "propose_order",
            "input": {
                "items": [
                    {"product_id": str(burger.id), "quantity": 1, "option_ids": [], "note": ""}
                ]
            },
            "expect_error": True,
        },
        {"reply": "شنو الحجم اللي تريده؟"},
    )
    res = handle_message(b, c, "أريد برغر")
    assert res["proposal_id"] is None
    assert AIProposal.objects.count() == 0


def test_cross_tenant_product_cannot_be_proposed(shop):
    b, c, *_ = shop
    other = make_product(make_business(), name_ar="منتج محل ثاني")
    script(
        {
            "tool": "propose_order",
            "input": {
                "items": [
                    {"product_id": str(other.id), "quantity": 1, "option_ids": [], "note": ""}
                ]
            },
            "expect_error": True,
        },
        {"reply": "ما لكيته"},
    )
    assert handle_message(b, c, "x")["proposal_id"] is None


def test_business_info_tool_returns_facts(shop):
    b, c, *_ = shop
    script({"tool": "get_business_info", "input": {}, "expect_error": False}, {"reply": "ok"})
    handle_message(b, c, "شوكت تسدون؟")
    assert AIMessage.objects.filter(role="tool", tool_name="get_business_info").exists()


def test_disabled_or_not_entitled_falls_back(shop):
    b, c, *_ = shop
    b.settings.ai_enabled = False
    b.settings.save()
    with pytest.raises(DomainError) as exc:
        handle_message(b, c, "hi")
    assert exc.value.code == "ai_unavailable"
    free = make_business(plan="free")
    free.settings.ai_enabled = True
    free.settings.save()
    with pytest.raises(DomainError):
        handle_message(free, make_customer(free), "hi")


def test_provider_failure_falls_back(shop):
    b, c, *_ = shop
    script({"raise": "timeout"})
    with pytest.raises(DomainError) as exc:
        handle_message(b, c, "hi")
    assert exc.value.code == "ai_unavailable"
    assert AIMessage.objects.filter(error="timeout").exists()


def test_monthly_quota(shop):
    b, c, *_ = shop
    PlanEntitlement.objects.filter(plan=plan("pro"), feature_id="ai_messages_per_month").update(
        value=1
    )
    invalidate(b.id)
    script({"reply": "هلا"})
    handle_message(b, c, "هلا")
    with pytest.raises(DomainError) as exc:
        handle_message(b, c, "هلا ثاني")
    assert exc.value.code == "plan_limit_exceeded"


def test_handover_and_pii_masking(shop):
    b, c, *_ = shop
    res = handle_message(b, c, "أريد أحجي ويا موظف رقمي 07701234567")
    assert res["handed_over"]
    stored = AIMessage.objects.get(role="user").content
    assert "07701234567" not in stored
    # Subsequent messages bypass the AI and go to staff.
    res2 = handle_message(b, c, "وينكم؟")
    assert res2["handed_over"]
    assert mask_pii("+964 770 123 4567") == "[phone]"


def _msg(stop, content, tin, tout):
    blocks = []
    for c in content:
        blocks.append(SimpleNamespace(**c))
    return SimpleNamespace(
        model="claude-opus-5-5",
        stop_reason=stop,
        content=blocks,
        usage=SimpleNamespace(input_tokens=tin, output_tokens=tout),
    )


@pytest.fixture
def fake_claude(settings, monkeypatch):
    """Stub the SDK call (the SDK's own HTTP stack is not intercepted by respx)."""
    from apps.chatbot import providers

    settings.AI_PROVIDER = "anthropic"
    settings.AI_API_KEY = "test-key"
    calls, replies = [], []

    def create(**kwargs):
        calls.append(json.loads(json.dumps(kwargs, default=lambda o: o.__dict__)))
        return replies.pop(0)

    real_init = providers.AnthropicProvider.__init__

    def init(self):
        real_init(self)
        monkeypatch.setattr(self.client.beta.messages, "create", create)

    monkeypatch.setattr(providers.AnthropicProvider, "__init__", init)
    return calls, replies


def test_anthropic_provider_request_shape_and_tool_loop(shop, fake_claude):
    b, c, *_ = shop
    calls, replies = fake_claude
    replies += [
        _msg(
            "tool_use",
            [
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "search_catalog",
                    "input": {"query": "بيبسي"},
                }
            ],
            100,
            20,
        ),
        _msg("end_turn", [{"type": "text", "text": "عدنا بيبسي، تريد كم وحدة؟"}], 150, 30),
    ]
    res = handle_message(b, c, "عدكم بيبسي؟")
    assert res["reply"] == "عدنا بيبسي، تريد كم وحدة؟"
    first = calls[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["output_config"] == {"effort": "low"}
    assert first["fallbacks"] == "default"
    assert first["betas"] == ["server-side-fallback-2026-07-01"]
    assert all(t["strict"] for t in first["tools"])
    assert "tool_choice" not in first
    assert "Iraqi" in first["system"]
    tool_result = calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert "بيبسي" in tool_result["content"]
    msg = AIMessage.objects.get(role="assistant")
    assert (msg.tokens_in, msg.tokens_out) == (250, 50)


def test_anthropic_refusal_falls_back(shop, fake_claude):
    b, c, *_ = shop
    _, replies = fake_claude
    replies.append(_msg("refusal", [], 1, 0))
    with pytest.raises(DomainError) as exc:
        handle_message(b, c, "x")
    assert exc.value.code == "ai_unavailable"


def test_tool_round_limit(shop, fake_claude, settings):
    b, c, *_ = shop
    _, replies = fake_claude
    loop = [{"type": "tool_use", "id": "t", "name": "get_business_info", "input": {}}]
    replies += [_msg("tool_use", loop, 1, 1) for _ in range(settings.AI_MAX_TOOL_ROUNDS + 1)]
    with pytest.raises(DomainError):
        handle_message(b, c, "x")
