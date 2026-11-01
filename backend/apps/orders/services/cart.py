from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.businesses.models import Branch
from apps.customers.models import Customer
from apps.orders.models import Cart, CartItem, CartStatus
from apps.products.models import Product
from apps.products.services import ensure_orderable, validate_selection
from core.errors import DomainError, NotFoundError

MAX_QTY = 99
MAX_LINES = 50


def fingerprint(option_ids: list[Any]) -> str:
    joined = ",".join(sorted(str(i) for i in option_ids))
    return hashlib.sha256(joined.encode()).hexdigest()[:32] if joined else ""


def get_active_cart(customer: Customer, branch: Branch, create: bool = True) -> Cart | None:
    now = timezone.now()
    cart = Cart.objects.filter(customer=customer, branch=branch, status=CartStatus.ACTIVE).first()
    if cart and cart.expires_at <= now:
        cart.status = CartStatus.ABANDONED
        cart.save(update_fields=["status", "updated_at"])
        cart = None
    if cart is None and create:
        try:
            with transaction.atomic():
                cart = Cart.objects.create(
                    business_id=customer.business_id,
                    customer=customer,
                    branch=branch,
                    expires_at=now + timedelta(days=settings.CART_TTL_DAYS),
                )
        except IntegrityError:
            cart = Cart.objects.get(customer=customer, branch=branch, status=CartStatus.ACTIVE)
    return cart


def _touch(cart: Cart) -> None:
    cart.expires_at = timezone.now() + timedelta(days=settings.CART_TTL_DAYS)
    cart.save(update_fields=["expires_at", "updated_at"])


def _product(customer: Customer, product_id: Any) -> Product:
    product = (
        Product.objects.for_business(customer.business_id)
        .filter(id=product_id, is_archived=False)
        .first()
    )
    if product is None:
        raise NotFoundError({"product_id": str(product_id)})
    return product


@transaction.atomic
def add_item(
    customer: Customer,
    branch: Branch,
    product_id: Any,
    option_ids: list[Any],
    quantity: int = 1,
    note: str = "",
) -> CartItem:
    if not 1 <= quantity <= MAX_QTY:
        raise DomainError("validation_error", {"quantity": ["1-99"]}, 400)
    product = _product(customer, product_id)
    ensure_orderable(product, quantity)
    selection = validate_selection(product, option_ids)
    cart = get_active_cart(customer, branch)
    assert cart is not None
    Cart.objects.select_for_update().filter(pk=cart.pk).first()
    fp = fingerprint([o.id for o in selection.options])
    note = note.strip()[:200]
    item = CartItem.objects.filter(
        cart=cart, product=product, options_fingerprint=fp, note=note
    ).first()
    if item:
        item.quantity = min(item.quantity + quantity, MAX_QTY)
        ensure_orderable(product, item.quantity)
        item.save(update_fields=["quantity", "updated_at"])
    else:
        if cart.items.count() >= MAX_LINES:
            raise DomainError("validation_error", {"cart": ["too many lines"]}, 400)
        item = CartItem.objects.create(
            business_id=customer.business_id,
            cart=cart,
            product=product,
            quantity=quantity,
            note=note,
            options_fingerprint=fp,
        )
        item.options.set(selection.options)
    _touch(cart)
    return item


def _item(customer: Customer, item_id: Any) -> CartItem:
    item = (
        CartItem.objects.select_related("cart", "product")
        .filter(id=item_id, cart__customer=customer, cart__status=CartStatus.ACTIVE)
        .first()
    )
    if item is None:
        raise NotFoundError({"item_id": str(item_id)})
    return item


def update_item_quantity(customer: Customer, item_id: Any, quantity: int) -> CartItem | None:
    item = _item(customer, item_id)
    if quantity <= 0:
        item.delete()
        return None
    if quantity > MAX_QTY:
        raise DomainError("validation_error", {"quantity": ["1-99"]}, 400)
    ensure_orderable(item.product, quantity)
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    _touch(item.cart)
    return item


def remove_item(customer: Customer, item_id: Any) -> None:
    _item(customer, item_id).delete()


def clear(customer: Customer, branch: Branch) -> None:
    cart = get_active_cart(customer, branch, create=False)
    if cart:
        cart.items.all().delete()


@dataclass
class PricedLine:
    item: CartItem
    unit_price: int
    line_total: int
    available: bool
    warning: str = ""
    options: tuple[Any, ...] = ()


@dataclass
class PricedCart:
    cart: Cart | None
    lines: list[PricedLine] = field(default_factory=list)
    subtotal: int = 0

    @property
    def has_problems(self) -> bool:
        return any(not line.available for line in self.lines)

    @property
    def item_count(self) -> int:
        return sum(line.item.quantity for line in self.lines)


def price_cart(cart: Cart | None) -> PricedCart:
    """Server-side pricing from current DB prices; flags lines that can no longer be ordered."""
    priced = PricedCart(cart=cart)
    if cart is None:
        return priced
    items = cart.items.select_related("product").prefetch_related(
        "options", "product__option_groups__options", "product__images"
    )
    for item in items:
        try:
            ensure_orderable(item.product, item.quantity)
            sel = validate_selection(item.product, [o.id for o in item.options.all()])
            line = PricedLine(
                item, sel.unit_price, sel.unit_price * item.quantity, True, options=sel.options
            )
        except DomainError as exc:
            unit = item.product.price + sum(o.price_delta for o in item.options.all())
            line = PricedLine(item, unit, 0, False, exc.code, tuple(item.options.all()))
        priced.lines.append(line)
        priced.subtotal += line.line_total
    return priced
