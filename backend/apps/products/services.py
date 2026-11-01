from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet

from apps.categories.models import Category
from apps.products.models import Availability, Option, OptionGroup, Product, SelectionType
from apps.subscriptions import services as entitlements
from core.errors import DomainError
from core.text import normalize_arabic


@dataclass(frozen=True)
class PricedSelection:
    unit_price: int
    options: tuple[Option, ...]


def validate_selection(product: Product, option_ids: Iterable[Any]) -> PricedSelection:
    """Validate chosen options against the product's groups and price them from the DB."""
    ids = {str(i) for i in option_ids}
    groups = list(product.option_groups.prefetch_related("options").all())
    by_id: dict[str, Option] = {}
    for g in groups:
        for o in g.options.all():
            by_id[str(o.id)] = o
    unknown = ids - set(by_id)
    if unknown:
        raise DomainError("invalid_options", {"unknown": sorted(unknown)}, 400)
    chosen: list[Option] = []
    for g in groups:
        picked = [by_id[i] for i in ids if by_id[i].group_id == g.id]
        if any(not o.is_available for o in picked):
            raise DomainError("invalid_options", {"group": str(g.id), "reason": "unavailable"})
        if len(picked) < g.effective_min:
            raise DomainError("invalid_options", {"group": str(g.id), "reason": "required"}, 400)
        max_allowed = 1 if g.selection_type == SelectionType.SINGLE else g.max_select
        if len(picked) > max_allowed:
            raise DomainError("invalid_options", {"group": str(g.id), "reason": "too_many"}, 400)
        chosen.extend(sorted(picked, key=lambda o: (o.sort_order, str(o.id))))
    unit_price = product.price + sum(o.price_delta for o in chosen)
    return PricedSelection(unit_price=unit_price, options=tuple(chosen))


def ensure_orderable(product: Product, quantity: int = 1) -> None:
    if not product.is_orderable:
        raise DomainError("product_unavailable", {"product_id": str(product.id)})
    if product.track_stock and (product.stock_quantity or 0) < quantity:
        raise DomainError(
            "insufficient_stock",
            {"product_id": str(product.id), "available": product.stock_quantity or 0},
        )


def storefront_products(business_id: Any) -> QuerySet[Product]:
    return (
        Product.objects.for_business(business_id)
        .filter(is_archived=False, category__is_active=True, category__is_archived=False)
        .exclude(availability=Availability.HIDDEN)
        .select_related("category")
        .prefetch_related("images", "option_groups__options")
    )


def search(qs: QuerySet[Product], query: str) -> QuerySet[Product]:
    terms = normalize_arabic(query).split()
    if not terms:
        return qs
    cond = Q()
    for term in terms[:6]:
        cond &= Q(search_text__icontains=term)
    return qs.filter(cond)


def _active_product_count(business_id: Any) -> int:
    return Product.objects.for_business(business_id).filter(is_archived=False).count()


def create_product(business_id: Any, **data: Any) -> Product:
    entitlements.check_limit(business_id, "max_products", _active_product_count(business_id))
    _check_category(business_id, data.get("category"))
    _check_stock(data)
    return Product.objects.create(business_id=business_id, **data)


def update_product(product: Product, **data: Any) -> Product:
    if "category" in data:
        _check_category(product.business_id, data["category"])
    merged = {
        "track_stock": data.get("track_stock", product.track_stock),
        "stock_quantity": data.get("stock_quantity", product.stock_quantity),
    }
    _check_stock(merged)
    for k, v in data.items():
        setattr(product, k, v)
    product.save()
    return product


def archive_product(product: Product) -> None:
    product.is_archived = True
    product.save(update_fields=["is_archived", "updated_at"])


def _check_category(business_id: Any, category: Category | None) -> None:
    if category is not None and str(category.business_id) != str(business_id):
        raise DomainError("validation_error", {"category": ["not found"]}, 400)


def _check_stock(data: dict[str, Any]) -> None:
    if data.get("track_stock") and data.get("stock_quantity") is None:
        raise DomainError("validation_error", {"stock_quantity": ["required"]}, 400)


def create_category(business_id: Any, **data: Any) -> Category:
    count = Category.objects.for_business(business_id).filter(is_archived=False).count()
    entitlements.check_limit(business_id, "max_categories", count)
    parent = data.get("parent")
    if parent is not None:
        if str(parent.business_id) != str(business_id):
            raise DomainError("validation_error", {"parent": ["not found"]}, 400)
        if parent.parent_id is not None:
            raise DomainError("validation_error", {"parent": ["max depth is 1"]}, 400)
    return Category.objects.create(business_id=business_id, **data)


def check_image_limit(product: Product) -> None:
    entitlements.check_limit(product.business_id, "max_images_per_product", product.images.count())


@transaction.atomic
def reorder(model: type[Any], business_id: Any, ordered_ids: list[Any]) -> None:
    objs = {
        str(o.id): o for o in model.objects.for_business(business_id).filter(id__in=ordered_ids)
    }
    for idx, oid in enumerate(ordered_ids):
        obj = objs.get(str(oid))
        if obj is not None:
            obj.sort_order = idx
            obj.save(update_fields=["sort_order", "updated_at"])


def create_option_group(product: Product, **data: Any) -> OptionGroup:
    if data.get("selection_type", SelectionType.SINGLE) == SelectionType.SINGLE:
        data["max_select"] = 1
    if data.get("is_required") and data.get("min_select", 0) == 0:
        data["min_select"] = 1
    return OptionGroup.objects.create(business_id=product.business_id, product=product, **data)


def create_option(group: OptionGroup, **data: Any) -> Option:
    return Option.objects.create(business_id=group.business_id, group=group, **data)
