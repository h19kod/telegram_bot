import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.orders.services import cart as cart_svc
from apps.orders.services.checkout import CheckoutInput, place_order
from apps.products.services import create_product
from apps.staff.models import Role
from apps.staff.services import create_invitation
from apps.subscriptions import services as ent
from apps.subscriptions.models import EntitlementOverride, PlanEntitlement, SubscriptionStatus
from core.errors import DomainError
from tests.factories import (
    branch_of,
    make_business,
    make_category,
    make_customer,
    make_product,
    plan,
)

pytestmark = pytest.mark.django_db


def test_plan_values_and_override_precedence():
    b = make_business(plan="free")
    assert ent.value(b.id, "max_products") == 20
    assert ent.has_feature(b.id, "ai_assistant") is False
    EntitlementOverride.objects.create(business=b, feature_id="max_products", value=500)
    ent.invalidate(b.id)
    assert ent.value(b.id, "max_products") == 500
    EntitlementOverride.objects.filter(business=b).update(
        expires_at=timezone.now() - timedelta(days=1)
    )
    ent.invalidate(b.id)
    assert ent.value(b.id, "max_products") == 20


def test_unlimited_is_null():
    b = make_business(plan="enterprise")
    assert ent.value(b.id, "max_products") is None
    ent.check_limit(b.id, "max_products", 10**6)


def test_product_limit_enforced():
    b = make_business(plan="free")
    PlanEntitlement.objects.filter(plan=plan("free"), feature_id="max_products").update(value=2)
    ent.invalidate(b.id)
    cat = make_category(b)
    create_product(b.id, category=cat, name_ar="a", price=1)
    create_product(b.id, category=cat, name_ar="b", price=1)
    with pytest.raises(DomainError) as exc:
        create_product(b.id, category=cat, name_ar="c", price=1)
    assert exc.value.code == "plan_limit_exceeded"


def test_staff_limit_enforced():
    b = make_business(plan="free")  # max_staff = 2, owner is 1
    role = Role.objects.get(business=b, name="Cashier")
    create_invitation(b, role, b.owner, email="a@x.com")
    from tests.factories import make_member

    make_member(b, "Cashier")
    with pytest.raises(DomainError):
        create_invitation(b, role, b.owner, email="b@x.com")


def test_monthly_order_quota_and_rollback_refund():
    b = make_business(plan="free")
    PlanEntitlement.objects.filter(plan=plan("free"), feature_id="max_orders_per_month").update(
        value=1
    )
    ent.invalidate(b.id)
    branch, customer = branch_of(b), make_customer(b)
    p = make_product(b)

    def checkout():
        cart_svc.add_item(customer, branch, p.id, [], 1)
        return place_order(
            customer,
            branch,
            CheckoutInput(
                fulfilment="pickup",
                customer_name="Ali",
                customer_phone="07701234567",
                idempotency_key=uuid.uuid4(),
            ),
        )

    checkout()
    with pytest.raises(DomainError) as exc:
        checkout()
    assert exc.value.code == "plan_limit_exceeded"
    assert ent.usage(b.id)["max_orders_per_month"] == 1


def test_feature_gate():
    b = make_business(plan="free")
    with pytest.raises(DomainError) as exc:
        ent.require_feature(b.id, "custom_bot")
    assert exc.value.code == "feature_not_available"


def test_trial_then_expiry_falls_back_to_default_plan():
    b = make_business(plan="pro")
    sub = ent.live_subscription(b.id)
    assert sub.status == SubscriptionStatus.TRIALING
    assert ent.has_feature(b.id, "ai_assistant")
    later = sub.current_period_end + timedelta(days=1)
    ent.expire_due_subscriptions(later)
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.PAST_DUE
    assert ent.has_feature(b.id, "ai_assistant")  # still during grace
    ent.expire_due_subscriptions(later + timedelta(days=ent.GRACE_DAYS + 1))
    sub.refresh_from_db()
    assert sub.status == SubscriptionStatus.EXPIRED
    assert not ent.has_feature(b.id, "ai_assistant")
    ent.extend_subscription(sub, 1)
    assert ent.has_feature(b.id, "ai_assistant")
