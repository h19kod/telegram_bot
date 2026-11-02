"""Order ratings: only the customer's own delivered order, within 7 days; staff replies."""

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.models import Order, OrderReview
from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.orders.services.reviews import rating_summary, reply_to_review, submit_review
from core.errors import DomainError, NotFoundError
from tests.factories import branch_of, make_business, make_customer, make_member, make_product
from tests.helpers import attach_bot, auth, init_data, internal

pytestmark = pytest.mark.django_db


def order_for(customer, delivered_days_ago: float | None = 0) -> Order:
    b = customer.business
    cart_svc.add_item(customer, branch_of(b), make_product(b, price=5000).id, [], 1)
    order, _ = place_order(
        customer,
        branch_of(b),
        CheckoutInput(
            fulfilment="pickup",
            customer_name="Ali",
            customer_phone="07701234567",
            idempotency_key=uuid.uuid4(),
        ),
    )
    if delivered_days_ago is not None:
        at = timezone.now() - timedelta(days=delivered_days_ago)
        Order.objects.filter(pk=order.pk).update(status="delivered", delivered_at=at)
    return Order.objects.get(pk=order.pk)


def test_customer_rates_and_updates_own_delivered_order():
    c = make_customer(make_business())
    o = order_for(c)
    r = submit_review(c, o.id, 4, "  طيب بس تأخر  ")
    assert (r.rating, r.comment) == (4, "طيب بس تأخر")
    r = submit_review(c, o.id, 5, "")
    assert OrderReview.objects.get().rating == 5
    assert rating_summary(c.business) == {"rating_avg": 5.0, "rating_count": 1}


@pytest.mark.parametrize("days", [None, 8])
def test_not_delivered_or_too_late_is_refused(days):
    c = make_customer(make_business())
    o = order_for(c, delivered_days_ago=days)
    with pytest.raises(DomainError) as e:
        submit_review(c, o.id, 5)
    assert e.value.code == "review_not_allowed"


@pytest.mark.parametrize("rating", [0, 6, "5", None])
def test_rating_must_be_1_to_5(rating):
    c = make_customer(make_business())
    with pytest.raises(DomainError):
        submit_review(c, order_for(c).id, rating)


def test_other_customers_order_is_not_found():
    b = make_business()
    o = order_for(make_customer(b))
    with pytest.raises(NotFoundError):
        submit_review(make_customer(b), o.id, 5)
    other = make_customer(make_business())
    with pytest.raises(NotFoundError):
        submit_review(other, o.id, 5)


def test_reply_and_clear_reply():
    c = make_customer(make_business())
    r = submit_review(c, order_for(c).id, 2, "بارد")
    r = reply_to_review(c.business, r.id, None, "نعتذر، راح نعوضك")
    assert r.reply
    assert r.replied_at
    r = reply_to_review(c.business, r.id, None, "")
    assert (r.reply, r.replied_at) == ("", None)
    with pytest.raises(NotFoundError):
        reply_to_review(make_business(), r.id, None, "x")


def test_mini_app_review_flow_and_store_rating(api):
    b = make_business()
    attach_bot(b)
    r = api.post(
        f"/api/v1/store/{b.slug}/session", {"init_data": init_data(user_id=31)}, format="json"
    )
    assert r.json()["business"]["rating_count"] == 0
    assert r.json()["business"]["rating_avg"] is None
    api.credentials(HTTP_AUTHORIZATION=f"Customer {r.json()['token']}")
    from apps.customers.models import Customer

    o = order_for(Customer.objects.get(telegram_user_id=31))
    base = f"/api/v1/store/{b.slug}"
    detail = api.get(f"{base}/orders/{o.id}").json()
    assert (detail["can_review"], detail["review"]) == (True, None)

    r = api.post(f"{base}/orders/{o.id}/review", {"rating": 9}, format="json")
    assert r.status_code == 400
    r = api.post(f"{base}/orders/{o.id}/review", {"rating": 4, "comment": "زين"}, format="json")
    assert r.status_code == 200, r.json()
    assert r.json()["review"] == {"rating": 4, "comment": "زين", "reply": ""}
    info = api.get(f"{base}/").json()
    assert (info["rating_avg"], info["rating_count"]) == (4.0, 1)


def test_bot_review_endpoint(api):
    b = make_business()
    bot = attach_bot(b)
    internal(api, "POST", f"/internal/v1/bots/{bot.id}/session", {"user": {"id": 77}})
    from apps.customers.models import Customer

    o = order_for(Customer.objects.get(telegram_user_id=77))
    r = internal(
        api,
        "POST",
        f"/internal/v1/bots/{bot.id}/customers/77/orders/{o.id}/review",
        {"rating": 5},
    )
    assert r.status_code == 200, r.json()
    assert r.json()["review"]["rating"] == 5
    assert r.json()["can_review"] is True  # still editable within the window


def test_dashboard_lists_summarises_and_replies(api):
    c = make_customer(make_business())
    b = c.business
    submit_review(c, order_for(c).id, 2, "بارد")
    submit_review(c, order_for(c).id, 5)
    auth(api, b.owner)
    rows = api.get(f"/api/v1/b/{b.id}/reviews?rating=2").json()["results"]
    assert [x["comment"] for x in rows] == ["بارد"]
    s = api.get(f"/api/v1/b/{b.id}/reviews/summary").json()
    assert s == {
        "rating_avg": 3.5,
        "rating_count": 2,
        "distribution": {"1": 0, "2": 1, "3": 0, "4": 0, "5": 1},
    }
    r = api.post(f"/api/v1/b/{b.id}/reviews/{rows[0]['id']}/reply", {"reply": "نعتذر"})
    assert r.status_code == 200
    assert r.json()["reply"] == "نعتذر"

    kitchen = make_member(b, "Kitchen")
    auth(api, kitchen.user)
    assert api.get(f"/api/v1/b/{b.id}/reviews").status_code == 200
    r = api.post(f"/api/v1/b/{b.id}/reviews/{rows[0]['id']}/reply", {"reply": "x"})
    assert r.status_code == 403
