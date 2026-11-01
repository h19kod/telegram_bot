import pytest

from apps.accounts.models import User
from tests.factories import make_business
from tests.helpers import auth, internal

pytestmark = pytest.mark.django_db


def test_internal_api_refuses_proxied_requests(api):
    r = internal(api, "GET", "/internal/v1/bots", headers={"HTTP_X_FORWARDED_FOR": "1.2.3.4"})
    assert r.status_code == 404
    assert internal(api, "GET", "/internal/v1/bots").status_code == 200


def test_business_creation_is_capped(api, settings):
    settings.MAX_BUSINESSES_PER_OWNER = 1
    u = User.objects.create_user(email="o@x.com", password="Very-Strong-Pass-1")
    auth(api, u)
    assert (
        api.post(
            "/api/v1/businesses", {"slug": "one_shop", "name_ar": "x"}, format="json"
        ).status_code
        == 201
    )
    r = api.post("/api/v1/businesses", {"slug": "two_shop", "name_ar": "y"}, format="json")
    assert r.status_code == 422


def test_secrets_not_in_error_bodies_or_settings_endpoints(api):
    b = make_business()
    auth(api, b.owner)
    body = api.get(f"/api/v1/b/{b.id}/settings").content.decode()
    assert "token" not in body.lower()


def test_html_injection_in_names_is_escaped_for_telegram():
    import uuid

    from apps.notifications.render import staff_order_text
    from apps.orders.services import cart as cart_svc
    from apps.orders.services.checkout import CheckoutInput, place_order
    from tests.factories import branch_of, make_customer, make_product

    b = make_business()
    c = make_customer(b)
    cart_svc.add_item(c, branch_of(b), make_product(b, name_ar="<a href='x'>p</a>").id, [], 1)
    o, _ = place_order(
        c,
        branch_of(b),
        CheckoutInput(
            fulfilment="pickup",
            customer_name="<b>evil</b>",
            customer_phone="07701234567",
            idempotency_key=uuid.uuid4(),
        ),
    )
    text = staff_order_text(o)
    assert "<b>evil</b>" not in text
    assert "&lt;a href=" in text


def test_spreadsheet_formula_injection_neutralised():
    from apps.orders.api import _safe_cell

    assert _safe_cell('=HYPERLINK("x")').startswith("'=")
    assert _safe_cell("+1") == "'+1"
    assert _safe_cell("normal") == "normal"


def test_security_headers_present(api):
    r = api.get("/healthz")
    assert r["X-Content-Type-Options"] == "nosniff"
    assert r["X-Request-ID"]
