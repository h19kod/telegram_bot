from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import Prefetch
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.request import Request
from rest_framework.response import Response

from apps.categories.models import Category
from apps.products import services as catalog
from apps.products.models import Availability, Option, OptionGroup, Product, ProductImage
from core.errors import NotFoundError
from core.images import validate_and_process_image
from core.tenancy import TenantPrimaryKeyRelatedField, TenantViewSet, require

PRICE_FIELDS = {"price", "compare_at_price"}


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = [
            "id",
            "name_ar",
            "name_en",
            "price_delta",
            "is_available",
            "is_default",
            "sort_order",
        ]
        read_only_fields = ["id"]


class OptionGroupSerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = OptionGroup
        fields = [
            "id",
            "name_ar",
            "name_en",
            "selection_type",
            "is_required",
            "min_select",
            "max_select",
            "sort_order",
            "options",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        inst = self.instance
        sel = attrs.get("selection_type", getattr(inst, "selection_type", "single"))
        mn = attrs.get("min_select", getattr(inst, "min_select", 0))
        mx = attrs.get("max_select", getattr(inst, "max_select", 1))
        if sel == "single":
            attrs["max_select"] = mx = 1
            mn = min(mn, 1)
            attrs["min_select"] = mn
        if mn > mx or mx < 1:
            raise serializers.ValidationError({"max_select": "must be >= min_select and >= 1"})
        return attrs


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "thumbnail", "width", "height", "sort_order", "alt_ar", "alt_en"]
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    category = TenantPrimaryKeyRelatedField(queryset=Category.objects.filter(is_archived=False))
    images = ProductImageSerializer(many=True, read_only=True)
    option_groups = OptionGroupSerializer(many=True, read_only=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, max_length=10
    )

    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "sku",
            "price",
            "compare_at_price",
            "availability",
            "track_stock",
            "stock_quantity",
            "prep_time_min",
            "tags",
            "sort_order",
            "images",
            "option_groups",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        price = attrs.get("price", getattr(self.instance, "price", None))
        cap = attrs.get("compare_at_price", getattr(self.instance, "compare_at_price", None))
        if price is not None and price < 0:
            raise serializers.ValidationError({"price": "must be >= 0"})
        if cap is not None and price is not None and cap <= price:
            raise serializers.ValidationError({"compare_at_price": "must be greater than price"})
        stock = attrs.get("stock_quantity", getattr(self.instance, "stock_quantity", None))
        if stock is not None and stock < 0:
            raise serializers.ValidationError({"stock_quantity": "must be >= 0"})
        return attrs


class ProductFilter(filters.FilterSet):
    category = filters.UUIDFilter(field_name="category_id")
    availability = filters.ChoiceFilter(choices=Availability.choices)
    search = filters.CharFilter(method="filter_search")

    class Meta:
        model = Product
        fields = ["category", "availability", "track_stock"]

    def filter_search(self, qs, name, value):  # type: ignore[no-untyped-def]
        return catalog.search(qs, value)


class BulkAvailabilitySerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), max_length=500)
    availability = serializers.ChoiceField(choices=Availability.choices)


class ProductViewSet(TenantViewSet):
    model = Product
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    ordering_fields = ["sort_order", "name_ar", "price", "created_at", "stock_quantity"]
    ordering = ["sort_order", "created_at"]
    required_permissions = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "write": ["catalog.edit"],
    }

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return (
            self.base_queryset()
            .filter(is_archived=False)
            .select_related("category")
            .prefetch_related(
                "images",
                Prefetch("option_groups", OptionGroup.objects.prefetch_related("options")),
            )
        )

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        require(self.request, "catalog.edit_prices")
        serializer.instance = catalog.create_product(self.business.id, **serializer.validated_data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        data = serializer.validated_data
        if PRICE_FIELDS & set(data) and any(
            data[f] != getattr(serializer.instance, f) for f in PRICE_FIELDS & set(data)
        ):
            require(self.request, "catalog.edit_prices")
        catalog.update_product(serializer.instance, **data)

    def perform_destroy(self, instance: Product) -> None:
        catalog.archive_product(instance)

    @action(detail=False, methods=["post"])
    def reorder(self, request: Request, business_id: Any) -> Response:
        ids = serializers.ListField(child=serializers.UUIDField()).run_validation(
            request.data.get("ids", [])
        )
        catalog.reorder(Product, self.business.id, ids)
        return Response(status=204)

    @action(detail=False, methods=["post"], url_path="bulk-availability")
    def bulk_availability(self, request: Request, business_id: Any) -> Response:
        s = BulkAvailabilitySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        n = (
            self.base_queryset()
            .filter(id__in=s.validated_data["ids"])
            .update(availability=s.validated_data["availability"])
        )
        return Response({"updated": n})

    @action(detail=True, methods=["post"])
    def duplicate(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        src = self.get_object()
        with transaction.atomic():
            copy = catalog.create_product(
                self.business.id,
                category=src.category,
                name_ar=f"{src.name_ar} (نسخة)",
                name_en=f"{src.name_en} (copy)" if src.name_en else "",
                description_ar=src.description_ar,
                description_en=src.description_en,
                price=src.price,
                compare_at_price=src.compare_at_price,
                availability=Availability.HIDDEN,
                track_stock=src.track_stock,
                stock_quantity=src.stock_quantity,
                prep_time_min=src.prep_time_min,
                tags=list(src.tags),
            )
            for g in src.option_groups.prefetch_related("options"):
                ng = OptionGroup.objects.create(
                    business_id=copy.business_id,
                    product=copy,
                    name_ar=g.name_ar,
                    name_en=g.name_en,
                    selection_type=g.selection_type,
                    is_required=g.is_required,
                    min_select=g.min_select,
                    max_select=g.max_select,
                    sort_order=g.sort_order,
                )
                for o in g.options.all():
                    Option.objects.create(
                        business_id=copy.business_id,
                        group=ng,
                        name_ar=o.name_ar,
                        name_en=o.name_en,
                        price_delta=o.price_delta,
                        is_available=o.is_available,
                        is_default=o.is_default,
                        sort_order=o.sort_order,
                    )
        return Response(
            ProductSerializer(
                self.get_queryset().get(pk=copy.pk), context=self.get_serializer_context()
            ).data,
            status=201,
        )

    @action(detail=True, methods=["post"], url_path="images")
    def upload_image(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        product = self.get_object()
        catalog.check_image_limit(product)
        processed = validate_and_process_image(request.FILES.get("image"))
        img = ProductImage.objects.create(
            business_id=product.business_id,
            product=product,
            image=processed.image,
            thumbnail=processed.thumbnail,
            width=processed.width,
            height=processed.height,
            sort_order=product.images.count(),
            alt_ar=request.data.get("alt_ar", "")[:150],
            alt_en=request.data.get("alt_en", "")[:150],
        )
        return Response(ProductImageSerializer(img).data, status=201)

    @extend_schema(
        parameters=[OpenApiParameter("image_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_id>[^/.]+)")
    def delete_image(
        self, request: Request, business_id: Any, pk: Any = None, image_id: Any = None
    ) -> Response:
        product = self.get_object()
        img = product.images.filter(id=image_id).first()
        if img is None:
            raise NotFoundError()
        img.image.delete(save=False)
        if img.thumbnail:
            img.thumbnail.delete(save=False)
        img.delete()
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="images/reorder")
    def reorder_images(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        product = self.get_object()
        ids = [str(i) for i in request.data.get("ids", [])]
        for idx, img in enumerate(
            sorted(
                product.images.all(),
                key=lambda i: ids.index(str(i.id)) if str(i.id) in ids else 999,
            )
        ):
            img.sort_order = idx
            img.save(update_fields=["sort_order", "updated_at"])
        return Response(status=204)

    @action(detail=True, methods=["get", "post"], url_path="option-groups")
    def option_groups(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        product = self.get_object()
        if request.method == "GET":
            return Response(OptionGroupSerializer(product.option_groups.all(), many=True).data)
        s = OptionGroupSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        group = catalog.create_option_group(product, **s.validated_data)
        return Response(OptionGroupSerializer(group).data, status=201)


class OptionGroupViewSet(TenantViewSet):
    model = OptionGroup
    serializer_class = OptionGroupSerializer
    required_permissions = {
        "list": ["catalog.view"],
        "retrieve": ["catalog.view"],
        "write": ["catalog.edit"],
    }
    http_method_names = ["get", "patch", "delete", "post"]
    pagination_class = None

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return self.base_queryset().prefetch_related("options")

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        raise MethodNotAllowed("POST")

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        if any(k == "price_delta" for k in serializer.validated_data):
            require(self.request, "catalog.edit_prices")
        serializer.save()

    @action(detail=True, methods=["post"])
    def options(self, request: Request, business_id: Any, pk: Any = None) -> Response:
        group = self.get_object()
        s = OptionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data.get("price_delta"):
            require(request, "catalog.edit_prices")
        opt = catalog.create_option(group, **s.validated_data)
        return Response(OptionSerializer(opt).data, status=201)


class OptionViewSet(TenantViewSet):
    model = Option
    serializer_class = OptionSerializer
    required_permissions = {"retrieve": ["catalog.view"], "write": ["catalog.edit"]}
    http_method_names = ["get", "patch", "delete"]

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        raise MethodNotAllowed("GET")

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        if "price_delta" in serializer.validated_data and (
            serializer.validated_data["price_delta"] != serializer.instance.price_delta
        ):
            require(self.request, "catalog.edit_prices")
        serializer.save()
