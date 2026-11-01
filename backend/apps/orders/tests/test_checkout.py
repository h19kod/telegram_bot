import uuid
from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.businesses.models import BusinessStatus, WorkingHours
from apps.notifications.models import NotificationOutbox
from apps.orders.models import Cart, CartStatus, Order, OrderStatus
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order, quote
from apps.products.models import Availability
from core.errors import DomainError
from tests.factories import (
    branch_of,
    make_business,
    make_customer,
    make_option,
    make_option_group,
    make_product,
    make_zone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop():
    b = make_business()
    return b, branch_of(b), make_customer(b), make_zone(b, fee=2000, free_delivery_threshold=50000)


def delivery_input(zone, **kw):
    data = {
        "fulfilment": "delivery",
        "customer_name": "علي حسين",
        "customer_phone": "07701234567",
        "idempotency_key": uuid.uuid4(),
        "zone_id": zone.id,
        "address_area": "الكرادة داخل",
        "address_landmark": "قرب جامع",
        "channel": "bot",
    }
    data.update(kw)
    return CheckoutInput(**data)


def test_place_order_reprices_and_snapshots(shop):
    b, branch, customer, zone = shop
    p = make_product(b, price=8000)
    size = make_option_group(p, is_required=True, min_select=1)
    large = make_option(size, name_ar="كبير", price_delta=1500)
    extras = make_option_group(p, name_ar="إضافات", selection_type="multiple", max_select=3)
    cheese = make_option(extras, name_ar="جبن", price_delta=500)
    cart_svc.add_item(customer, branch, p.id, [large.id, cheese.id], quantity=2)

    order, created = place_order(customer, branch, delivery_input(zone))

    assert created
    assert order.number == 1001
    assert order.subtotal == (8000 + 1500 + 500) * 2
    assert order.delivery_fee == 2000
    assert order.total == 22000
    assert order.customer_phone == "+9647701234567"
    item = order.items.get()
    assert item.unit_price == 10000
    assert item.product_name_ar == "برغر دبل"
    assert {o.option_name_ar for o in item.options.all()} == {"كبير", "جبن"}
    assert order.events.get().to_status == OrderStatus.PENDING
    assert Cart.objects.get(customer=customer).status == CartStatus.CONVERTED
    assert NotificationOutbox.objects.filter(dedup_key=f"order:{order.id}:placed").exists()

    # Price change after ordering does not affect the snapshot.
    p.price = 1
    p.save()
    item.refresh_from_db()
    assert item.unit_price == 10000


def test_idempotent_checkout(shop):
    b, branch, customer, zone = shop
    p = make_product(b)
    cart_svc.add_item(customer, branch, p.id, [], 1)
    data = delivery_input(zone)
    o1, c1 = place_order(customer, branch, data)
    o2, c2 = place_order(customer, branch, data)
    assert (c1, c2) == (True, False)
    assert o1.id == o2.id
    assert Order.objects.count() == 1


def test_free_delivery_threshold(shop):
    b, branch, customer, zone = shop
    p = make_product(b, price=25000)
    cart_svc.add_item(customer, branch, p.id, [], 2)
    order, _ = place_order(customer, branch, delivery_input(zone))
    assert order.delivery_fee == 0


def test_pickup_has_no_fee_or_address(shop):
    b, branch, customer, _ = shop
    p = make_product(b, price=5000)
    cart_svc.add_item(customer, branch, p.id, [], 1)
    data = CheckoutInput(
        fulfilment="pickup",
        customer_name="Ali",
        customer_phone="0780 111 2233",
        idempotency_key=uuid.uuid4(),
        address_area="should be ignored",
    )
    order, _ = place_order(customer, branch, data)
    assert order.delivery_fee == 0
    assert order.address_area == ""
    assert order.payment_method == "pay_at_pickup"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda ctx: (
                ctx["product"].__setattr__("availability", Availability.OUT_OF_STOCK)
                or ctx["product"].save()
            ),
            "product_unavailable",
        ),
        (
            lambda ctx: (
                ctx["business"].__setattr__("status", BusinessStatus.SUSPENDED)
                or ctx["business"].save()
            ),
            "business_unavailable",
        ),
        (
            lambda ctx: ctx["customer"].__setattr__("is_blocked", True) or ctx["customer"].save(),
            "customer_blocked",
        ),
        (
            lambda ctx: (
                ctx["branch"].__setattr__("is_temporarily_closed", True) or ctx["branch"].save()
            ),
            "outside_working_hours",
        ),
        (
            lambda ctx: ctx["zone"].__setattr__("is_active", False) or ctx["zone"].save(),
            "delivery_zone_invalid",
        ),
        (
            lambda ctx: (
                ctx["settings"].__setattr__("min_order_amount", 100000) or ctx["settings"].save()
            ),
            "below_minimum_order",
        ),
    ],
)
def test_checkout_rules(shop, mutate, code):
    b, branch, customer, zone = shop
    p = make_product(b)
    cart_svc.add_item(customer, branch, p.id, [], 1)
    mutate(
        {
            "product": p,
            "business": b,
            "customer": customer,
            "branch": branch,
            "zone": zone,
            "settings": b.settings,
        }
    )
    customer.refresh_from_db()
    with pytest.raises(DomainError) as exc:
        place_order(customer, branch, delivery_input(zone))
    assert exc.value.code == code
    assert Order.objects.count() == 0


@pytest.mark.parametrize(
    ("kw", "code"),
    [
        ({"customer_phone": "12345"}, "invalid_phone"),
        ({"zone_id": None}, "delivery_zone_required"),
        ({"address_area": ""}, "address_required"),
        ({"address_landmark": "", "address_street": ""}, "address_required"),
        ({"payment_method": "pay_at_pickup"}, "payment_method_unavailable"),
        ({"idempotency_key": None}, "idempotency_key_required"),
    ],
)
def test_checkout_input_validation(shop, kw, code):
    b, branch, customer, zone = shop
    cart_svc.add_item(customer, branch, make_product(b).id, [], 1)
    with pytest.raises(DomainError) as exc:
        place_order(customer, branch, delivery_input(zone, **kw))
    assert exc.value.code == code


def test_empty_cart(shop):
    _, branch, customer, zone = shop
    with pytest.raises(DomainError) as exc:
        place_order(customer, branch, delivery_input(zone))
    assert exc.value.code == "cart_empty"


def test_required_option_enforced(shop):
    b, branch, customer, _ = shop
    p = make_product(b)
    g = make_option_group(p, is_required=True, min_select=1)
    make_option(g)
    with pytest.raises(DomainError) as exc:
        cart_svc.add_item(customer, branch, p.id, [], 1)
    assert exc.value.code == "invalid_options"


def test_single_select_rejects_two_options(shop):
    b, branch, customer, _ = shop
    p = make_product(b)
    g = make_option_group(p)
    o1, o2 = make_option(g), make_option(g, name_ar="صغير")
    with pytest.raises(DomainError):
        cart_svc.add_item(customer, branch, p.id, [o1.id, o2.id], 1)


def test_foreign_option_rejected(shop):
    b, branch, customer, _ = shop
    p = make_product(b)
    other = make_product(b, name_ar="بيبسي")
    foreign = make_option(make_option_group(other))
    with pytest.raises(DomainError):
        cart_svc.add_item(customer, branch, p.id, [foreign.id], 1)


def test_cart_merges_identical_lines(shop):
    b, branch, customer, _ = shop
    p = make_product(b)
    cart_svc.add_item(customer, branch, p.id, [], 1)
    cart_svc.add_item(customer, branch, p.id, [], 2)
    cart = cart_svc.get_active_cart(customer, branch)
    assert cart.items.get().quantity == 3


def test_stock_decrement_and_insufficient(shop):
    b, branch, customer, zone = shop
    p = make_product(b, track_stock=True, stock_quantity=2)
    cart_svc.add_item(customer, branch, p.id, [], 2)
    place_order(customer, branch, delivery_input(zone))
    p.refresh_from_db()
    assert p.stock_quantity == 0
    assert not p.is_orderable
    with pytest.raises(DomainError) as exc:
        cart_svc.add_item(customer, branch, p.id, [], 1)
    assert exc.value.code == "product_unavailable"


def test_working_hours_crossing_midnight(shop):
    from apps.businesses.services import is_open

    b, branch, *_ = shop
    now = timezone.localtime()
    WorkingHours.objects.create(
        business=b,
        branch=branch,
        weekday=(now.weekday() - 1) % 7,
        opens_at=time(18, 0),
        closes_at=time(2, 0),
    )
    at_1am = now.replace(hour=1, minute=0)
    at_noon = now.replace(hour=12, minute=0)
    assert is_open(branch, at_1am)
    assert not is_open(branch, at_noon)
    at_night_yesterday = at_1am - timedelta(hours=4)  # 21:00 yesterday
    assert is_open(branch, at_night_yesterday)


def test_quote_matches_order(shop):
    b, branch, customer, zone = shop
    cart_svc.add_item(customer, branch, make_product(b, price=7000).id, [], 3)
    data = delivery_input(zone)
    q = quote(customer, branch, data)
    order, _ = place_order(customer, branch, data)
    assert (q.subtotal, q.delivery_fee, q.total) == (
        order.subtotal,
        order.delivery_fee,
        order.total,
    )


def test_too_many_open_orders(shop, settings):
    settings.MAX_OPEN_ORDERS_PER_CUSTOMER = 1
    b, branch, customer, zone = shop
    p = make_product(b)
    cart_svc.add_item(customer, branch, p.id, [], 1)
    place_order(customer, branch, delivery_input(zone))
    cart_svc.add_item(customer, branch, p.id, [], 1)
    with pytest.raises(DomainError) as exc:
        place_order(customer, branch, delivery_input(zone))
    assert exc.value.code == "too_many_open_orders"
