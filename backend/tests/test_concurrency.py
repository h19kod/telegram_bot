"""Real parallel transactions against PostgreSQL (separate connections per thread)."""

import threading
import uuid

import pytest
from django.db import connection

from apps.orders.models import EventSource, Order, OrderStatus
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.orders.services.transitions import transition
from core.errors import DomainError
from tests.factories import (
    branch_of,
    make_business,
    make_customer,
    make_product,
    owner_membership,
)

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


def run_parallel(fn, n):
    results, errors = [], []
    barrier = threading.Barrier(n)

    def worker():
        try:
            barrier.wait()
            results.append(fn())
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, errors


def pickup(key):
    return CheckoutInput(
        fulfilment="pickup",
        customer_name="Ali",
        customer_phone="07701234567",
        idempotency_key=key,
    )


def test_same_idempotency_key_creates_one_order():
    b = make_business()
    branch, customer = branch_of(b), make_customer(b)
    cart_svc.add_item(customer, branch, make_product(b).id, [], 1)
    key = uuid.uuid4()
    results, errors = run_parallel(lambda: place_order(customer, branch, pickup(key)), 8)
    assert not errors
    assert Order.objects.count() == 1
    assert sum(created for _, created in results) == 1


def test_last_stock_unit_sold_once():
    b = make_business()
    branch = branch_of(b)
    p = make_product(b, track_stock=True, stock_quantity=1)
    customers = [make_customer(b) for _ in range(5)]
    for c in customers:
        cart_svc.add_item(c, branch, p.id, [], 1)
    it = iter(customers)
    lock = threading.Lock()

    def buy():
        with lock:
            c = next(it)
        return place_order(c, branch, pickup(uuid.uuid4()))

    results, errors = run_parallel(buy, 5)
    assert len(results) == 1
    assert all(isinstance(e, DomainError) for e in errors)
    p.refresh_from_db()
    assert p.stock_quantity == 0


def test_order_numbers_unique_under_load():
    b = make_business()
    branch = branch_of(b)
    p = make_product(b)
    customers = [make_customer(b) for _ in range(10)]
    for c in customers:
        cart_svc.add_item(c, branch, p.id, [], 1)
    it = iter(customers)
    lock = threading.Lock()

    def buy():
        with lock:
            c = next(it)
        return place_order(c, branch, pickup(uuid.uuid4()))

    results, errors = run_parallel(buy, 10)
    assert not errors
    numbers = sorted(o.number for o, _ in results)
    assert numbers == list(range(1001, 1011))


def test_parallel_transitions_apply_once():
    b = make_business()
    branch, customer = branch_of(b), make_customer(b)
    cart_svc.add_item(customer, branch, make_product(b).id, [], 1)
    order, _ = place_order(customer, branch, pickup(uuid.uuid4()))
    owner = owner_membership(b)

    def press():
        return transition(
            business_id=b.id,
            order_id=order.id,
            to=OrderStatus.CONFIRMED,
            source=EventSource.TELEGRAM,
            membership=owner,
            expected_version=1,
        )

    results, errors = run_parallel(press, 6)
    assert not errors
    assert sum(r.applied for r in results) == 1
    order.refresh_from_db()
    assert order.version == 2
    assert order.events.count() == 2
