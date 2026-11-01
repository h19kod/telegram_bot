"""Every tenant endpoint must hide other businesses' data (404), for every route."""

import re

import pytest
from django.urls import get_resolver

from apps.chatbot.models import AIConversation, KnowledgeEntry
from apps.orders.models import Coupon
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.platform_admin.models import SupportTicket
from apps.staff.models import Role, StaffInvitation
from config.urls import tenant
from tests.factories import (
    branch_of,
    make_business,
    make_customer,
    make_member,
    make_option,
    make_option_group,
    make_product,
    make_zone,
)
from tests.helpers import auth

pytestmark = pytest.mark.django_db


def build(b):
    import uuid

    p = make_product(b)
    g = make_option_group(p)
    o = make_option(g)
    c = make_customer(b)
    zone = make_zone(b)
    cart_svc.add_item(c, branch_of(b), p.id, [o.id], 1)
    order, _ = place_order(
        c,
        branch_of(b),
        CheckoutInput(
            fulfilment="pickup",
            customer_name="Ali",
            customer_phone="07701234567",
            idempotency_key=uuid.uuid4(),
        ),
    )
    member = make_member(b, "Cashier")
    inv = StaffInvitation.objects.create(
        business=b,
        role=Role.objects.get(business=b, name="Kitchen"),
        token_hash=uuid.uuid4().hex,
        expires_at="2099-01-01T00:00Z",
    )
    return {
        "branch": branch_of(b),
        "category": p.category,
        "product": p,
        "option-group": g,
        "option": o,
        "order": order,
        "customer": c,
        "delivery-zone": zone,
        "role": Role.objects.get(business=b, name="Cashier"),
        "member": member,
        "invitation": inv,
        "b-ticket": SupportTicket.objects.create(business=b, subject="x"),
        "knowledge": KnowledgeEntry.objects.create(business=b, topic="t", answer_ar="a"),
        "ai-conversation": AIConversation.objects.create(business=b, customer=c),
        "coupon": Coupon.objects.create(
            business=b, code=f"C{uuid.uuid4().hex[:8]}".upper(), kind="fixed", value=100
        ),
    }


def test_all_router_basenames_covered():
    covered = set(build.__code__.co_consts) | {
        "branch",
        "category",
        "product",
        "option-group",
        "option",
        "order",
        "customer",
        "delivery-zone",
        "role",
        "member",
        "invitation",
        "b-ticket",
        "knowledge",
        "ai-conversation",
        "coupon",
    }
    for _, _, basename in tenant.registry:
        assert basename in covered, f"{basename} missing from isolation matrix"


def test_cross_tenant_detail_routes_return_404(api):
    a, b = make_business(), make_business()
    objs_b = build(b)
    build(a)
    auth(api, a.owner)
    for prefix, _, basename in tenant.registry:
        obj = objs_b[basename]
        url = f"/api/v1/b/{a.id}/{prefix}/{obj.pk}"
        for method in ("get", "patch", "delete"):
            r = getattr(api, method)(url, {}, format="json")
            assert r.status_code in (404, 405), (method, url, r.status_code)
        obj.refresh_from_db()  # still exists (not deleted through A)


def test_cross_tenant_list_routes_hide_rows(api):
    a, b = make_business(), make_business()
    objs_b = build(b)
    build(a)
    auth(api, a.owner)
    for prefix, _, basename in tenant.registry:
        r = api.get(f"/api/v1/b/{a.id}/{prefix}")
        if r.status_code == 405:
            continue
        assert r.status_code == 200, (prefix, r.status_code, r.content[:200])
        body = r.json()
        rows = body["results"] if isinstance(body, dict) and "results" in body else body
        ids = {str(row.get("id")) for row in rows}
        assert str(objs_b[basename].pk) not in ids, prefix


def test_non_member_gets_404_for_every_business_url(api):
    a, b = make_business(), make_business()
    build(b)
    auth(api, a.owner)
    resolver = get_resolver()
    paths = [p for p in _all_paths(resolver) if p.startswith("api/v1/b/<uuid:business_id>/")]
    assert len(paths) > 30
    for raw in paths:
        if "<" in raw.replace("<uuid:business_id>", ""):
            continue  # detail routes are covered above
        url = "/" + raw.replace("<uuid:business_id>", str(b.id))
        r = api.get(url)
        assert r.status_code in (404, 405), (url, r.status_code)


def test_foreign_fk_rejected_on_create(api):
    a, b = make_business(), make_business()
    cat_b = make_product(b).category
    auth(api, a.owner)
    r = api.post(
        f"/api/v1/b/{a.id}/products",
        {"category": str(cat_b.id), "name_ar": "x", "price": 100},
        format="json",
    )
    assert r.status_code == 400
    assert "category" in r.json()["error"]["details"]


def test_business_field_cannot_be_injected(api):
    a, b = make_business(), make_business()
    auth(api, a.owner)
    r = api.post(
        f"/api/v1/b/{a.id}/categories", {"name_ar": "x", "business": str(b.id)}, format="json"
    )
    assert r.status_code == 201
    from apps.categories.models import Category

    assert Category.objects.get(id=r.json()["id"]).business_id == a.id


def _all_paths(resolver, prefix=""):
    for p in resolver.url_patterns:
        pat = prefix + str(p.pattern)
        if hasattr(p, "url_patterns"):
            yield from _all_paths(p, pat)
        else:
            yield re.sub(r"^\^|\$$", "", pat)
