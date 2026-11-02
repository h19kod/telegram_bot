"""OpenAPI contract: the schema generates cleanly and real responses match what it documents.

Many storefront/dashboard responses are built as dicts; their documented shapes live in
*/schema.py. These tests fail when a response gains, loses or retypes a field without the
schema being updated (the Mini App and dashboard types are generated from it).
"""

import re
import uuid
from functools import cache

import pytest
from django.core.management import call_command
from drf_spectacular.generators import SchemaGenerator

from apps.accounts.models import User
from tests.factories import make_business, make_option, make_option_group, make_product, make_zone
from tests.helpers import attach_bot, auth, init_data

pytestmark = pytest.mark.django_db


@cache
def schema() -> dict:
    return SchemaGenerator().get_schema(request=None, public=True)


def test_schema_generates_without_warnings(tmp_path):
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(tmp_path / "s.yaml"))
    assert not [p for p in schema()["paths"] if p.startswith("/internal")]


def test_committed_schema_is_current():
    """frontend/packages/shared/openapi.json (source of the TS types) must match the code."""
    import json
    from pathlib import Path

    committed = Path(__file__).resolve().parents[2] / "frontend/packages/shared/openapi.json"
    fresh = json.loads(json.dumps(schema(), default=str))
    assert json.loads(committed.read_text()) == fresh, "run `make schema` and commit the result"


def resolve(node: dict) -> dict:
    while "$ref" in node:
        node = schema()["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    if "allOf" in node and len(node["allOf"]) == 1:
        merged = {**resolve(node["allOf"][0]), **{k: v for k, v in node.items() if k != "allOf"}}
        return merged
    return node


TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def check(value, node: dict, where: str) -> None:
    node = resolve(node)
    if value is None:
        assert node.get("nullable"), f"{where}: null but not nullable"
        return
    if "oneOf" in node:
        errors = []
        for option in node["oneOf"]:
            try:
                check(value, option, where)
                return
            except AssertionError as exc:
                errors.append(str(exc))
        raise AssertionError(f"{where}: matches no oneOf option: {errors}")
    if "enum" in node:
        assert value in node["enum"], f"{where}: {value!r} not in {node['enum']}"
    expected = node.get("type", "object" if "properties" in node else None)
    if expected is None:
        return  # free-form
    py = TYPES[expected]
    wrong = f"{where}: expected {expected}, got {type(value).__name__} {value!r}"
    assert isinstance(value, py), wrong
    assert not (expected in ("integer", "number") and isinstance(value, bool)), wrong
    if expected == "array":
        for i, item in enumerate(value):
            check(item, node.get("items", {}), f"{where}[{i}]")
    elif expected == "object" and "properties" in node:
        props = node["properties"]
        assert set(value) <= set(props), f"{where}: undocumented {sorted(set(value) - set(props))}"
        missing = set(node.get("required", [])) - set(value)
        assert not missing, f"{where}: missing {sorted(missing)}"
        for key, sub in props.items():
            if key in value:
                check(value[key], sub, f"{where}.{key}")
    elif expected == "object" and isinstance(node.get("additionalProperties"), dict):
        for key, sub in value.items():
            check(sub, node["additionalProperties"], f"{where}.{key}")


def operation(path: str, method: str) -> tuple[str, dict]:
    for template, item in schema()["paths"].items():
        pattern = "^" + re.sub(r"\{[^/]+\}", "[^/]+", template) + "$"
        if re.match(pattern, path) and method in item:
            return template, item[method]
    raise AssertionError(f"{method.upper()} {path} is not in the OpenAPI schema")


def conforms(response, method: str) -> dict:
    path = response.wsgi_request.path
    template, op = operation(path, method)
    code = str(response.status_code)
    assert code in op["responses"], (
        f"{method.upper()} {template}: {code} {response.content[:300]!r}"
    )
    content = op["responses"][code].get("content")
    if response.status_code == 204:
        assert content is None
        return {}
    data = response.json()
    check(data, content["application/json"]["schema"], f"{method.upper()} {template}")
    return data


def test_storefront_responses_match_schema(api):
    b = make_business()
    attach_bot(b)
    p = make_product(b, price=6000)
    g = make_option_group(p, is_required=True, min_select=1)
    opt = make_option(g, price_delta=1000)
    zone = make_zone(b, fee=1500)
    base = f"/api/v1/store/{b.slug}"

    s = conforms(api.post(f"{base}/session", {"init_data": init_data()}, format="json"), "post")
    api.credentials(HTTP_AUTHORIZATION=f"Customer {s['token']}")
    for url in ("/", "/categories", "/products", f"/products/{p.id}", "/delivery-zones", "/cart"):
        conforms(api.get(f"{base}{url}"), "get")
    cart = conforms(
        api.post(
            f"{base}/cart/items",
            {"product_id": str(p.id), "option_ids": [str(opt.id)], "quantity": 2},
            format="json",
        ),
        "post",
    )
    line = cart["lines"][0]["id"]
    conforms(api.patch(f"{base}/cart/items/{line}", {"quantity": 3}, format="json"), "patch")
    body = {
        "fulfilment": "delivery",
        "customer_name": "Ali",
        "customer_phone": "07801112233",
        "zone_id": str(zone.id),
        "address_area": "Mansour",
        "address_landmark": "Near the mall",
    }
    conforms(api.post(f"{base}/checkout/quote", body, format="json"), "post")
    order = conforms(
        api.post(f"{base}/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())),
        "post",
    )
    conforms(api.get(f"{base}/orders"), "get")
    conforms(api.get(f"{base}/orders/{order['id']}"), "get")
    conforms(api.post(f"{base}/orders/{order['id']}/cancel", {}, format="json"), "post")
    conforms(api.get(f"{base}/me"), "get")
    conforms(api.patch(f"{base}/me", {"language": "en"}, format="json"), "patch")
    addr = conforms(
        api.post(f"{base}/me/addresses", {"area": "Karrada", "zone": str(zone.id)}, format="json"),
        "post",
    )
    conforms(api.get(f"{base}/me/addresses"), "get")
    conforms(api.delete(f"{base}/me/addresses/{addr['id']}"), "delete")
    conforms(api.post(f"{base}/support", {"message": "hello"}, format="json"), "post")


def test_dashboard_responses_match_schema(api):
    b = make_business()
    make_product(b)
    client = auth(api, b.owner)
    base = f"/api/v1/b/{b.id}"
    for url in (
        "/",
        "/analytics/overview",
        "/analytics/sales?interval=week",
        "/analytics/top-products",
        "/analytics/recent-customers",
        "/permissions",
        "/subscription",
        "/telegram",
        "/audit-log",
        "/products",
        "/orders",
        "/customers",
    ):
        conforms(client.get(f"{base}{url}"), "get")
    conforms(client.post("/api/v1/auth/telegram/link-code"), "post")
    conforms(client.post("/api/v1/auth/ws-ticket"), "post")


def test_auth_and_platform_responses_match_schema(api, settings):
    settings.PLATFORM_ADMIN_REQUIRE_2FA = False
    r = api.post(
        "/api/v1/auth/register",
        {"email": "new@x.com", "password": "Very-Strong-Pass-1", "full_name": "New"},
        format="json",
    )
    conforms(r, "post")
    admin = User.objects.create_user(
        email="root@x.com", password="Very-Strong-Pass-1", is_platform_admin=True
    )
    client = auth(api, admin)
    for url in (
        "/api/v1/platform/stats?days=7",
        "/api/v1/platform/health",
        "/api/v1/platform/audit-log",
    ):
        conforms(client.get(url), "get")
    for bad in ("/api/v1/platform/stats?days=abc", "/api/v1/platform/audit-log?business=nope"):
        r = client.get(bad)
        assert r.status_code == 400
        check(r.json(), schema()["components"]["schemas"]["Error"], bad)
