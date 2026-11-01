from __future__ import annotations

import itertools
from typing import Any

import factory

from apps.accounts.models import User
from apps.businesses.models import Branch, Business
from apps.businesses.services import create_business, default_branch
from apps.categories.models import Category
from apps.customers.models import Customer
from apps.delivery.models import DeliveryZone
from apps.products.models import Option, OptionGroup, Product
from apps.staff.models import Membership, Role
from apps.subscriptions.models import Plan

_seq = itertools.count(1)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Faker("name")
    password = factory.django.Password("Str0ng-Passw0rd!")


def make_business(owner: User | None = None, plan: str = "pro", **kw: Any) -> Business:
    owner = owner or UserFactory()
    n = next(_seq)
    business = create_business(
        owner,
        slug=kw.pop("slug", f"shop{n}"),
        name_ar=kw.pop("name_ar", f"مطعم {n}"),
        plan_code=plan,
        **kw,
    )
    return business


def branch_of(business: Business) -> Branch:
    return default_branch(business)


def make_member(business: Business, role_name: str, user: User | None = None) -> Membership:
    user = user or UserFactory()
    role = Role.objects.get(business=business, name=role_name)
    return Membership.objects.create(business=business, user=user, role=role)


def owner_membership(business: Business) -> Membership:
    return Membership.objects.select_related("role", "user").get(
        business=business, role__is_owner=True
    )


def make_category(business: Business, **kw: Any) -> Category:
    return Category.objects.create(business=business, name_ar=kw.pop("name_ar", "برغر"), **kw)


def make_product(business: Business, category: Category | None = None, **kw: Any) -> Product:
    category = category or make_category(business)
    kw.setdefault("name_ar", "برغر دبل")
    kw.setdefault("name_en", "Double burger")
    kw.setdefault("price", 8000)
    return Product.objects.create(business=business, category=category, **kw)


def make_option_group(product: Product, **kw: Any) -> OptionGroup:
    kw.setdefault("name_ar", "الحجم")
    return OptionGroup.objects.create(business_id=product.business_id, product=product, **kw)


def make_option(group: OptionGroup, **kw: Any) -> Option:
    kw.setdefault("name_ar", "كبير")
    return Option.objects.create(business_id=group.business_id, group=group, **kw)


def make_customer(business: Business, **kw: Any) -> Customer:
    kw.setdefault("telegram_user_id", 100000 + next(_seq))
    kw.setdefault("first_name", "Ali")
    return Customer.objects.create(business=business, **kw)


def make_zone(business: Business, **kw: Any) -> DeliveryZone:
    kw.setdefault("name_ar", "الكرادة")
    kw.setdefault("fee", 2000)
    return DeliveryZone.objects.create(business=business, branch=branch_of(business), **kw)


def plan(code: str) -> Plan:
    return Plan.objects.get(code=code)
